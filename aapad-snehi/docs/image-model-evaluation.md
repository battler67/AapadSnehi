# Image caption and vision-model evaluation

## Historical decision and current status

This evaluation originally selected `Qwen/Qwen3-VL-2B-Instruct` through Hugging
Face's routed provider. That provider is now deliberately disconnected from the
application because the current account/runtime capability did not provide a stable
working path. The implementation and research remain available for later reuse.

The active application uses hosted `gpt-4.1-mini` through OpenAI's Responses API.
It supports image input and strict structured output without downloading a model to
the local machine. This is an operational service choice, not a claim that it is an
open-source or universally superior disaster model.

The choice is operational, not a claim that Qwen is universally the most accurate
disaster classifier. Reliability here comes from structured output validation, an
independent deterministic hazard check, a narrow rejection rule, and human review
on every uncertain or failed path.

## Compared candidates

Provider availability was checked on 2026-08-21 and can change independently of the
model repositories.

| Candidate | Approximate size/class | Strengths | Constraints in this project | Result |
|---|---:|---|---|---|
| [GPT-4.1 mini](https://developers.openai.com/api/docs/models/gpt-4.1-mini) | Hosted proprietary service | Image input, instruction following, Responses API, strict structured output; no local RAM/model download | Paid external service; requires privacy, budget and availability controls; still needs human review | Active provider |
| [Qwen3-VL-2B-Instruct](https://huggingface.co/Qwen/Qwen3-VL-2B-Instruct) | 2.1B parameters | Modern instruction-following vision-language model; can caption and return constrained evidence in one call; Apache-2.0 | Current account/runtime route was not reliable enough for this app | Retained but inactive |
| [Florence-2-base-ft](https://huggingface.co/microsoft/Florence-2-base-ft) | About 0.23B parameters / 463 MB weights | Strong lightweight task-prompted captioning and vision tasks; MIT license; attractive self-host footprint | No routed provider mapping was available during evaluation; self-hosting would still need runtime RAM/compute | Preferred future self-hosted fallback |
| [SmolVLM-256M-Instruct](https://huggingface.co/blog/smolervlm) | About 0.26B parameters | Very small multimodal family designed for constrained devices; Apache-2.0 | No routed provider mapping was available during evaluation; smaller capacity may weaken subtle damage recognition and JSON consistency | Re-evaluate when remotely hosted and benchmarked |
| [BLIP image-captioning base](https://huggingface.co/Salesforce/blip-image-captioning-base) | Lightweight caption specialist | Simple, mature captioning model; legacy Space source already exists | COCO-style short captions omit context; the account's Space runtime was unavailable; no structured disaster evidence | Retained only as a legacy prototype |

Other compact caption specialists, including GIT-style models, had the same current
deployment problem: a model repository alone does not provide a callable hosted
runtime. Downloading any of them locally would directly conflict with the low-RAM
requirement.

## Why an instruction-following vision service over the smallest option

A raw scene caption is not enough for the desired workflow. The application needs
visible facts, a bounded yes/no/unclear evidence value, and hazards restricted to
the portal taxonomy. The active OpenAI model produces these together under a strict
structured-output request, while the backend independently validates every field.
The hosted route makes that capability usable without downloading weights.

The smaller Florence and SmolVLM candidates remain valuable if the project later
obtains a managed endpoint or separate inference host. Florence is the first fallback
to benchmark because its task-oriented design and much smaller weight footprint fit
the captioning requirement. Do not switch solely on parameter count: compare hazard
recall, hard-negative false rejection, ambiguity rate, JSON validity, Indian scene
coverage, latency, cost, and privacy posture on a consented evaluation set.

## Evaluation gates before production

1. Build a consented, de-identified set spanning each canonical hazard, ordinary
   scenes, old/news screenshots, edited images, low light, rain, smoke, rural roads,
   dense settlements, and multilingual text.
2. Measure the three final workflow outcomes, especially false rejection of genuine
   emergencies. Caption similarity metrics alone do not measure operational safety.
3. Report results by hazard, geography, lighting, image quality, and relevant
   demographic/environmental slices; inspect disagreements manually.
4. Pin model, provider, prompt, preprocessing, and policy versions. Re-run the suite
   before changing any one of them.
5. Retain the human-review fallback and provenance boundary even if accuracy
   improves. Image screening must not create official warnings or dispatch people
   autonomously.

OpenAI's [image-input guide](https://developers.openai.com/api/docs/guides/images-vision)
and [Responses API reference](https://developers.openai.com/api/reference/resources/responses/methods/create)
define the active request shape. Re-check model availability, privacy controls, and
pricing before deployment. Hugging Face provider mappings and account permissions
must likewise be re-evaluated before reconnecting the retained Qwen client.
