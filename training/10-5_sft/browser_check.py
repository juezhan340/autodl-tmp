"""用Playwright检查真实页面与隔离模拟指标，绝不启动正式训练。"""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from urllib.request import urlopen

from common import load_config, write_json


def check_layout(page, with_traces: bool = False) -> dict:
    """验证页面和文字边界、分区重叠，并检查canvas真实绘图像素。"""
    result = page.evaluate("""() => {
      const pixels = [...document.querySelectorAll('canvas')].map(canvas => {
        const values = canvas.getContext('2d').getImageData(0,0,canvas.width,canvas.height).data;
        let visible=0, trace=0;
        for(let i=0;i<values.length;i+=4) {
          if(values[i+3]>0) visible++;
          if(values[i]===0 && values[i+1]===133 && values[i+2]===117 && values[i+3]>0) trace++;
        }
        return {visible,trace};
      });
      const overflow=[];
      for(const element of document.querySelectorAll('h1,h2,.metric-value,.metric-note,.badge,.epoch-name,.gpu-numbers strong')) {
        const range=document.createRange(); range.selectNodeContents(element);
        const text=range.getBoundingClientRect(), box=element.getBoundingClientRect();
        if(text.width && (text.left < box.left-2 || text.right > box.right+2)) overflow.push(element.textContent);
      }
      const sections=[...document.querySelectorAll('.heading,.config-strip,.metrics,.epoch-section,.charts,.bottom,footer')];
      const overlap=[];
      sections.slice(1).forEach((section,index) => {
        if(section.getBoundingClientRect().top < sections[index].getBoundingClientRect().bottom-1) overlap.push(section.className);
      });
      return {width:innerWidth,contentWidth:document.documentElement.scrollWidth,canvasPixels:pixels,textOverflow:overflow,sectionOverlap:overlap};
    }""")
    assert result["contentWidth"] <= result["width"], result
    assert all(value["visible"] > 100 for value in result["canvasPixels"]), result
    assert not result["textOverflow"] and not result["sectionOverlap"], result
    if with_traces:
        assert all(value["trace"] > 100 for value in result["canvasPixels"]), result
    return result


def mock_running(snapshot: dict) -> dict:
    """构造仅浏览器路由可见的测试指标，不写正式训练状态。"""
    data = copy.deepcopy(snapshot)
    data["training"] = {"status": "running", "phase": "training", "epoch": 1.35, "global_step": 85, "max_steps": 189, "elapsed_seconds": 180, "gpu_allocated_mib": 15000, "gpu_reserved_mib": 19000, "gpu_peak_allocated_mib": 17000}
    data["metrics"] = [{"global_step": step, "epoch": step/63, "loss": 0.9-step*0.005, "learning_rate": 0.0001*(1-step/189)} for step in range(1, 86)]
    data["metrics"].append({"global_step": 63, "epoch": 1, "eval_loss": 0.5})
    data["checkpoints"] = [{"name": "checkpoint-63", "epoch": 1, "global_step": 63, "adapter_sha256": "a"*64, "best": False}]
    return data


def run_browser_check(url: str, output_dir: Path) -> dict:
    """检查桌面、手机、动态轮询和注入防护，将证据写到仓库外。"""
    from playwright.sync_api import expect, sync_playwright
    output_dir.mkdir(parents=True, exist_ok=True)
    with urlopen(url.rstrip("/") + "/api/status", timeout=10) as response:
        actual = json.loads(response.read())
    report = {"live_status": actual["training"]["status"], "live_effective_batch": actual["effective_batch"], "viewports": [], "training_started_by_check": False}
    errors = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=playwright.chromium.executable_path, headless=True, args=["--no-sandbox"])
        try:
            for name, width, height in (("desktop", 1440, 1000), ("mobile", 390, 844), ("narrow", 360, 800), ("wide", 1920, 1080)):
                page = browser.new_page(viewport={"width": width, "height": height}, device_scale_factor=1)
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(url, wait_until="networkidle")
                expect(page.locator("#connection")).to_contain_text("监控在线")
                assert page.locator("#micro").inner_text() == "4"
                assert page.locator("#accumulation").inner_text() == "2"
                layout = check_layout(page)
                page.screenshot(path=str(output_dir / f"live-{name}.png"), full_page=True)
                report["viewports"].append({"name": name, **layout})
                page.close()
            mock = mock_running(actual)
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.route("**/api/status", lambda route: route.fulfill(status=200, content_type="application/json", body=json.dumps(mock)))
            page.goto(url, wait_until="networkidle")
            expect(page.locator("#step")).to_have_text("85 / 189")
            assert page.locator("#checkpoints tr").count() == 1
            assert page.locator("#loss-empty").is_hidden()
            report["fixture_desktop_layout"] = check_layout(page, with_traces=True)
            page.screenshot(path=str(output_dir / "fixture-running-desktop.png"), full_page=True)
            mock["training"].update(global_step=86, epoch=1.365)
            mock["metrics"].append({"global_step": 86, "epoch": 1.365, "loss": 0.321, "learning_rate": 0.00005})
            expect(page.locator("#step")).to_have_text("86 / 189", timeout=10000)
            assert page.locator("#loss").inner_text() == "0.3210"
            report["dynamic_poll_updates"] = True
            mock["training"].update(status="completed", phase="completed", epoch=3, global_step=189, best_checkpoint="checkpoint-126")
            mock["checkpoints"] = [{"name": f"checkpoint-{epoch*63}", "epoch": epoch, "global_step": epoch*63, "best": epoch == 2} for epoch in (1, 2, 3)]
            expect(page.locator("#status")).to_have_text("训练完成", timeout=10000)
            assert page.locator("#checkpoints tr").count() == 3
            assert page.locator("#saved-count").inner_text() == "已保留 3 / 3"
            report["three_checkpoints_visible"] = True
            mock["training"].update(status="failed", error='<img src=x onerror="window.injected=true">')
            expect(page.locator("#status")).to_have_text("训练失败", timeout=10000)
            assert page.locator("#error img").count() == 0
            assert page.evaluate("window.injected === undefined")
            report["error_text_is_not_html"] = True
            page.close()
            mobile = browser.new_page(viewport={"width": 390, "height": 844})
            mobile.route("**/api/status", lambda route: route.fulfill(status=200, content_type="application/json", body=json.dumps(mock_running(actual))))
            mobile.goto(url, wait_until="networkidle")
            expect(mobile.locator("#step")).to_have_text("85 / 189")
            report["fixture_mobile_layout"] = check_layout(mobile, with_traces=True)
            mobile.screenshot(path=str(output_dir / "fixture-running-mobile.png"), full_page=True)
            mobile.close()
        finally:
            browser.close()
    assert not errors, errors
    report["page_errors"] = errors
    report["fixture_data_written_to_live_server"] = False
    write_json(output_dir / "browser_report.json", report)
    return report


def main() -> None:
    """可选浏览器验证只访问展示服务，不加载模型或调用训练入口。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:6008")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    output = args.output_dir or Path(load_config()["output_root"]) / "monitor_checks"
    print(run_browser_check(args.url, output))


if __name__ == "__main__":
    main()
