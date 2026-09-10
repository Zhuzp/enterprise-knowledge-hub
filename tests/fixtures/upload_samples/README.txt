上传测试样例文件
==================

目录: tests/fixtures/upload_samples/

documents/  — 文档（light 解析队列）
  差旅报销制度.txt      纯文本，最快验证上传→解析
  差旅报销制度.md       Markdown
  差旅报销制度.pdf      PDF（pymupdf 生成）
  员工手册摘要.docx     Word
  部门人员.csv          CSV 表格
  部门预算.xlsx         Excel

images/  — 图片（light 队列）
  流程说明.png          含中文说明的测试图
  封面图.jpg            JPEG 测试图

media/  — 音视频（heavy 解析队列）
  会议录音样例.wav      2 秒 440Hz 正弦波，ffprobe 可识别
  语音备忘.mp3          最小 MP3 占位（仅验证上传/入队）
  培训片段.mp4          最小 MP4 占位；完整视频测试见下方

重新生成全部文件:
  python scripts/generate_test_fixtures.py

生成真实可解析的 MP4（需本机安装 ffmpeg 并加入 PATH）:
  python scripts/generate_test_fixtures.py
  或手动:
  ffmpeg -y -f lavfi -i color=c=0x2b5797:s=640x360:d=3 ^
    -f lavfi -i sine=frequency=880:duration=3 ^
    -c:v libx264 -pix_fmt yuv420p -c:a aac -shortest ^
    tests/fixtures/upload_samples/media/培训片段.mp4

上传示例（PowerShell，先 login 拿 token）:

  $token = "YOUR_ACCESS_TOKEN"
  curl.exe -X POST "http://127.0.0.1:8000/api/v1/documents" `
    -H "Authorization: Bearer $token" `
    -F "file=@tests/fixtures/upload_samples/documents/差旅报销制度.txt" `
    -F "title=差旅制度测试"

测试建议顺序:
  1. txt / md / csv     → light 队列，秒级解析
  2. pdf / docx / xlsx  → light 队列，稍慢
  3. png / jpg          → light 队列，OCR 占位
  4. wav                → heavy 队列，ASR（当前为 mock）
  5. mp4                → heavy 队列，需 ffmpeg 生成真实文件
