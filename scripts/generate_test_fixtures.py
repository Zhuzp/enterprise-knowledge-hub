"""生成上传测试样例文件到 tests/fixtures/upload_samples/"""

from __future__ import annotations

import csv
import io
import struct
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "tests" / "fixtures" / "upload_samples"

# 企业知识库测试用中文内容
POLICY_TEXT = """差旅报销制度（测试文档）

一、适用范围
本制度适用于全体员工因公出差产生的交通、住宿、餐饮等费用报销。

二、住宿标准
- 一线城市：500 元/晚
- 二线城市：350 元/晚
- 其他城市：280 元/晚

三、交通标准
- 高铁/动车：二等座
- 飞机：经济舱，需提前 3 天申请

四、报销流程
1. 填写差旅申请单
2. 部门负责人审批
3. 财务审核票据
4. 5 个工作日内到账

联系人：财务部 张三，分机 8001
"""

EMPLOYEES_CSV_ROWS = [
    ["姓名", "部门", "职级", "常驻城市"],
    ["张三", "研发部", "P6", "北京"],
    ["李四", "财务部", "P5", "上海"],
    ["王五", "人力资源", "P4", "杭州"],
    ["赵六", "市场部", "P5", "深圳"],
]


def ensure_dirs() -> None:
    for sub in ("documents", "media", "images"):
        (OUT / sub).mkdir(parents=True, exist_ok=True)


def write_text_files() -> None:
    (OUT / "documents" / "差旅报销制度.txt").write_text(POLICY_TEXT, encoding="utf-8")
    md = f"# 差旅报销制度\n\n{POLICY_TEXT}\n\n> 本文件用于上传测试。\n"
    (OUT / "documents" / "差旅报销制度.md").write_text(md, encoding="utf-8")


def write_csv() -> None:
    path = OUT / "documents" / "部门人员.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerows(EMPLOYEES_CSV_ROWS)


def write_xlsx() -> None:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "2025预算"
    ws.append(["项目", "Q1", "Q2", "Q3", "Q4"])
    ws.append(["差旅费", 50000, 60000, 55000, 48000])
    ws.append(["培训费", 20000, 15000, 18000, 22000])
    ws.append(["办公用品", 8000, 9000, 8500, 9000])
    wb.save(OUT / "documents" / "部门预算.xlsx")


def write_docx() -> None:
    from docx import Document

    doc = Document()
    doc.add_heading("员工手册摘要（测试）", level=0)
    doc.add_paragraph(POLICY_TEXT)
    doc.add_heading("考勤说明", level=1)
    doc.add_paragraph("工作时间：9:00-18:00，弹性打卡 30 分钟。")
    doc.save(OUT / "documents" / "员工手册摘要.docx")


def write_pdf() -> None:
    import fitz

    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((50, 50), POLICY_TEXT, fontsize=11)
    doc.save(OUT / "documents" / "差旅报销制度.pdf")
    doc.close()


def write_png() -> None:
    import fitz

    doc = fitz.open()
    page = doc.new_page(width=480, height=240)
    page.draw_rect(fitz.Rect(0, 0, 480, 240), color=(0.95, 0.95, 0.95), fill=(0.95, 0.95, 0.95))
    page.insert_text(
        (20, 40),
        "企业知识库测试图片\n\n报销流程：申请 → 审批 → 财务审核",
        fontsize=14,
    )
    pix = page.get_pixmap(dpi=150)
    pix.save(str(OUT / "images" / "流程说明.png"))
    doc.close()


def write_jpg() -> None:
    import fitz

    doc = fitz.open()
    page = doc.new_page(width=320, height=180)
    page.insert_text((20, 60), "测试 JPG 图片\n上传解析用", fontsize=16)
    pix = page.get_pixmap(dpi=120)
    pix.save(str(OUT / "images" / "封面图.jpg"))
    doc.close()


def write_wav() -> None:
    """1 秒 440Hz 正弦波，ffprobe/ffmpeg 可识别"""
    path = OUT / "media" / "会议录音样例.wav"
    sample_rate = 16000
    duration = 2
    freq = 440.0
    import math

    samples = []
    for i in range(sample_rate * duration):
        val = int(16000 * math.sin(2 * math.pi * freq * i / sample_rate))
        samples.append(val)

    with wave.open(str(path), "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(struct.pack(f"<{len(samples)}h", *samples))


def write_minimal_mp3() -> None:
    """极短合法 MP3（约 0.1s 静音），用于上传/解析队列测试"""
    # 来源：公开域最小 MP3 测试帧
    mp3_bytes = bytes.fromhex(
        "fff348c400000000000000000000000000000000000000000000000000"
        "000000000000000000000000000000000000000000000000000000000000"
    )
    # 使用更可靠的短 MP3（ID3 + frame）
    minimal = (
        b"\xff\xfb\x90\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
        b"\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
        b"\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
        b"\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
    )
    (OUT / "media" / "语音备忘.mp3").write_bytes(minimal)


def write_mp4_with_ffmpeg() -> bool:
    import shutil
    import subprocess

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return False
    out = OUT / "media" / "培训片段.mp4"
    cmd = [
        ffmpeg,
        "-y",
        "-f", "lavfi",
        "-i", "color=c=0x2b5797:s=640x360:d=3",
        "-f", "lavfi",
        "-i", "sine=frequency=880:duration=3",
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-shortest",
        str(out),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return True


def write_minimal_mp4() -> None:
    """无 ffmpeg 时写入最小 ftyp box，至少可通过上传校验"""
    # 最小 MP4 容器（无实际音视频，parse 可能失败但 upload 可用）
    data = (
        b"\x00\x00\x00\x20ftypisom\x00\x00\x02\x00isomiso2mp41"
        b"\x00\x00\x00\x08free"
        b"\x00\x00\x00\x08mdat"
    )
    (OUT / "media" / "培训片段.mp4").write_bytes(data)


def write_readme() -> None:
    text = """上传测试样例文件
==================

目录说明
  documents/  文档类（light 解析队列）
  images/     图片类（light 队列）
  media/      音视频（heavy 解析队列，需 ffmpeg 才能完整解析视频）

推荐测试顺序
  1. documents/差旅报销制度.txt   — 最快验证上传→解析
  2. documents/部门人员.csv       — 表格解析
  3. documents/差旅报销制度.pdf   — PDF 解析
  4. images/流程说明.png          — 图片 OCR
  5. media/会议录音样例.wav       — 音频 ASR（heavy 队列）
  6. media/培训片段.mp4           — 视频（需 ffmpeg 生成才有真实内容）

curl 上传示例（先 login 拿 token）:

  curl -X POST http://127.0.0.1:8000/api/v1/documents \\
    -H "Authorization: Bearer YOUR_TOKEN" \\
    -F "file=@tests/fixtures/upload_samples/documents/差旅报销制度.txt" \\
    -F "title=差旅制度测试"

重新生成: python scripts/generate_test_fixtures.py
"""
    (OUT / "README.txt").write_text(text, encoding="utf-8")


def main() -> None:
    ensure_dirs()
    write_text_files()
    write_csv()
    write_xlsx()
    write_docx()
    write_pdf()
    write_png()
    write_jpg()
    write_wav()
    write_minimal_mp3()
    if not write_mp4_with_ffmpeg():
        write_minimal_mp4()
        print("未检测到 ffmpeg，已生成最小 MP4 占位文件（上传可用，解析可能失败）")
    write_readme()
    print(f"已生成测试文件到: {OUT}")
    for p in sorted(OUT.rglob("*")):
        if p.is_file():
            print(f"  {p.relative_to(ROOT)}  ({p.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
