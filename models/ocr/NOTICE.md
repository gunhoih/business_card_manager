# Model attribution

These ONNX models are converted from PaddleOCR models by RapidAI/RapidOCR.

- PaddleOCR: https://github.com/PaddlePaddle/PaddleOCR (Copyright PaddlePaddle Authors)
- RapidOCR: https://github.com/RapidAI/RapidOCR (RapidAI and contributors)
- Official model registry: https://github.com/RapidAI/RapidOCR/blob/v3.10.0/python/rapidocr/default_models.yaml
- Model source and license statement: https://rapidai.github.io/RapidOCRDocs/latest/en/model_licenses/
- License: Apache License, Version 2.0; see LICENSE-APACHE-2.0.txt.

Model files are not modified by this project; only their local filenames differ.

| Local file | Upstream artifact |
|---|---|
| detection.onnx | ch_PP-OCRv5_det_mobile.onnx |
| korean_recognition.onnx | korean_PP-OCRv5_rec_mobile.onnx |
| english_recognition.onnx | en_PP-OCRv5_rec_mobile.onnx |
| orientation.onnx | ch_PP-LCNet_x0_25_textline_ori_cls_mobile.onnx |

The app downloads missing or invalid models on first OCR use, verifies their pinned SHA-256 values and caches them in this directory. The optional command `uv run python scripts/setup_rapidocr.py --smoke-test` prepares and tests the same files in advance. No placeholder model files are supplied or required in Git. The OCR inference itself remains local to the app server.
