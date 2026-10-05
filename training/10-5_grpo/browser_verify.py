"""只访问GRPO监控页面，检查真实桌面/手机布局、曲线与轮询，不启动训练。"""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from urllib.request import urlopen

from runtime import write_json


def check_layout(page, require_traces):
    """检测页面溢出、关键文字和区段重叠，并读取canvas实际像素。"""
    result = page.evaluate("""() => {
      const overflow=[];
      for(const element of document.querySelectorAll('h1,h2,.value,.status,.pair strong')){
        const range=document.createRange();range.selectNodeContents(element);
        const text=range.getBoundingClientRect(),box=element.getBoundingClientRect();
        if(text.width && (text.left<box.left-2 || text.right>box.right+2))overflow.push(element.textContent);
      }
      const sections=[...document.querySelectorAll('.heading,.strip,.metrics,.progress-band,.charts,.details,.bottom')];
      const overlaps=sections.slice(1).filter((s,i)=>s.getBoundingClientRect().top<sections[i].getBoundingClientRect().bottom-1).length;
      const pixels=[...document.querySelectorAll('canvas')].map(c=>{const p=c.getContext('2d').getImageData(0,0,c.width,c.height).data;let visible=0,trace=0;for(let i=0;i<p.length;i+=4){if(p[i+3])visible++;if(p[i]===0 && p[i+1]===133 && p[i+2]===117 && p[i+3])trace++;}return {visible,trace};});
      return {viewport:innerWidth,contentWidth:document.documentElement.scrollWidth,overflow,overlaps,pixels};
    }""")
    assert result["contentWidth"] <= result["viewport"] and not result["overflow"] and not result["overlaps"], result
    assert all(item["visible"] > 100 for item in result["pixels"]), result
    if require_traces:
        assert all(item["trace"] > 10 for item in result["pixels"]), result
    return result


def verify(url, output):
    """真实页面截图加浏览器内隔离夹具验证，不写正式状态或奖励。"""
    from playwright.sync_api import expect, sync_playwright
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    with urlopen(url.rstrip("/") + "/api/status", timeout=10) as response:
        actual = json.loads(response.read())
    report = {"live_status": actual["training"]["status"], "micro": actual["config"]["micro_batch"], "accumulation": actual["config"]["accumulation"], "viewports": [], "formal_state_modified": False}
    errors = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=["--no-sandbox"])
        try:
            for name, width, height in (("desktop", 1440, 1080), ("mobile", 390, 844), ("narrow", 360, 800), ("wide", 1920, 1080)):
                page = browser.new_page(viewport={"width": width, "height": height}, device_scale_factor=1)
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(url, wait_until="networkidle")
                expect(page.locator("#connection")).to_contain_text("监控在线")
                expect(page.locator("#micro")).to_have_text("16")
                expect(page.locator("#accumulation")).to_have_text("1")
                report["viewports"].append({"name": name, **check_layout(page, bool(actual["metrics"]))})
                page.screenshot(path=str(output / f"live-{name}.png"), full_page=True)
                page.close()
            fixture = copy.deepcopy(actual)
            fixture["training"].update(global_step=10, status="running", phase="backward")
            page = browser.new_page(viewport={"width": 1440, "height": 1080})
            page.route("**/api/status", lambda route: route.fulfill(status=200, content_type="application/json", body=json.dumps(fixture)))
            page.goto(url, wait_until="networkidle")
            expect(page.locator("#step")).to_have_text("10 / 25")
            fixture["training"]["global_step"] = 11
            expect(page.locator("#step")).to_have_text("11 / 25", timeout=10000)
            report["dynamic_poll_verified"] = True
            fixture["training"].update(status="failed", error='<img src=x onerror="window.injected=true">')
            expect(page.locator("#status")).to_have_text("执行失败", timeout=10000)
            assert page.locator("#error img").count() == 0 and page.evaluate("window.injected === undefined")
            report["error_injection_blocked"] = True
            page.close()
        finally:
            browser.close()
    assert not errors, errors
    report["page_errors"] = errors
    write_json(output / "browser_report.json", report)
    return report


def main():
    """截图写仓库外，既可访问本机也可验证平台公网地址。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:6008")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(verify(args.url, args.output))


if __name__ == "__main__":
    main()
