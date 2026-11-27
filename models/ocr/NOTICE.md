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

Run `uv run python scripts/setup_rapidocr.py --smoke-test` from the repository root to acquire and verify the four actual binaries. No placeholder models are supplied. The app uses only the verified local models and does not download model files during inference.
