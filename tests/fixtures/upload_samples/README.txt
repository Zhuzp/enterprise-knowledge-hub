上传测试样例文件
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

  curl -X POST http://127.0.0.1:8000/api/v1/documents \
    -H "Authorization: Bearer YOUR_TOKEN" \
    -F "file=@tests/fixtures/upload_samples/documents/差旅报销制度.txt" \
    -F "title=差旅制度测试"

重新生成: python scripts/generate_test_fixtures.py
