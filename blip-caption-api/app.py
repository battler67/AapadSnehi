from __future__ import annotations

import os

import gradio as gr
import spaces
import torch
from PIL import Image
from transformers import BlipForConditionalGeneration, BlipProcessor


MODEL_ID = os.getenv("MODEL_ID", "Salesforce/blip-image-captioning-base").strip()
MAX_IMAGE_PIXELS = 25_000_000
MAX_CAPTION_CHARS = 300

Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS

processor = BlipProcessor.from_pretrained(MODEL_ID)
model = BlipForConditionalGeneration.from_pretrained(
    MODEL_ID,
    torch_dtype=torch.float16,
).to("cuda")
model.eval()


@spaces.GPU(duration=30)
def caption_image(image: Image.Image | None) -> tuple[str, str]:
    if image is None:
        raise gr.Error("Choose a JPEG, PNG, or WebP image")
    if image.width * image.height > MAX_IMAGE_PIXELS:
        raise gr.Error("Decoded image dimensions are too large")
    rgb_image = image.convert("RGB")
    inputs = processor(images=rgb_image, return_tensors="pt").to("cuda", torch.float16)
    with torch.inference_mode():
        output = model.generate(**inputs, max_new_tokens=40, num_beams=3)
    caption = " ".join(processor.decode(output[0], skip_special_tokens=True).split())
    if not caption:
        raise gr.Error("The model returned an empty caption")
    return caption[:MAX_CAPTION_CHARS], MODEL_ID


demo = gr.Interface(
    fn=caption_image,
    inputs=gr.Image(
        type="pil",
        image_mode="RGB",
        sources=["upload", "webcam"],
        label="Disaster evidence image",
    ),
    outputs=[
        gr.Textbox(label="Caption"),
        gr.Textbox(label="Model"),
    ],
    title="AapadSnehi BLIP Caption API",
    description=(
        "Hosted scene captions for report triage. A caption does not establish "
        "authenticity, location, recency, or official disaster status."
    ),
    api_name="caption",
    flagging_mode="never",
)
demo.queue(max_size=2, default_concurrency_limit=1)
