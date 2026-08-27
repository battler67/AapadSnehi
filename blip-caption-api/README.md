---
title: Blip Caption Api
emoji: 📷
colorFrom: indigo
colorTo: pink
sdk: gradio
python_version: 3.12.12
app_file: app.py
pinned: false
short_description: Legacy BLIP caption prototype for AapadSnehi
models:
  - Salesforce/blip-image-captioning-base
---

# BLIP caption API

> **Legacy prototype:** AapadSnehi's active image-screening integration now uses
> `Qwen/Qwen3-VL-2B-Instruct` through the Hugging Face routed Inference Providers
> API. This Space is retained for reproducibility and possible captioning
> experiments, but the application no longer calls it and it remains superseded.

This Gradio Space hosts `Salesforce/blip-image-captioning-base` for AapadSnehi
citizen-report triage. Once eligible compute is activated, model weights are
downloaded and loaded inside Hugging Face's runtime, not on the AapadSnehi client
or backend host. The Gradio app is prepared for ZeroGPU, but the account must first
become eligible to select that hardware.

The named `/caption` Gradio API accepts one image and returns the caption and model
ID. Call it with the lightweight Python client:

```python
from gradio_client import Client, handle_file

client = Client("mural13/blip-caption-api")
caption, model = client.predict(
    handle_file("evidence.jpg"),
    api_name="/caption",
)
```

The Space bounds decoded image dimensions, emits only a short caption, and allows
one inference at a time. Disaster triage policy remains independently replaceable
inside AapadSnehi.
