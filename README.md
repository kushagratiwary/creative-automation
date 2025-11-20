# Creative Automation Pipeline

This repository implements an end-to-end system that automatically transforms a structured YAML marketing brief into production-ready ad creatives using:

- Gemini 2.5 Flash Image for generating background scenes  
- A deterministic layout engine for text and logo overlays  
- A Gemini-driven compliance + quality review loop  

The project is packaged as `creative_pipeline` and is executed via:  
`python -m creative_pipeline.cli`

---

## 1. High-Level Overview

Given a YAML campaign brief, the pipeline:

1. Loads brand and product details.
2. For each product and each required aspect ratio:
   - Generates a product-centric background image using Gemini.
   - Fits/crops the image with a reserved lower zone for text.
   - Applies marketing copy and brand logo overlays.
   - Runs an optional legal, brand, and quality review loop.
3. Outputs final creatives into a structured directory.
4. Logs all processing steps for visibility and debugging.

---

## 2. Requirements

### Python Version
- Python **3.10+** (recommended: 3.11)

### Install Dependencies
```
pip install -r requirements.txt
```

If installing manually:
```
pip install pillow pyyaml google-genai
```

---

## 3. Environment Variables

Before running the pipeline, set your Gemini API key.

### Linux / macOS
```
export GEMINI_API_KEY="your_api_key_here"
```

### Windows PowerShell
```
$env:GEMINI_API_KEY="your_api_key_here"
```

---

## 4. Project Structure

```
creative_pipeline/
    cli.py
    brief_loader.py
    models.py
    image_generator.py
    utils.py
    processor.py
    compliance_and_review.py

examples/
    campaign_brief_*.yaml
    product_images/

output/
    (generated creatives appear here)
```

---

## 5. File-by-File Walkthrough

### `models.py`
Defines:
- Brand metadata
- Product metadata
- CampaignBrief structure

### `brief_loader.py`
- Loads YAML briefs  
- Validates and constructs a `CampaignBrief`

### `cli.py`
- CLI entry point  
- Parses arguments, configures logging, runs generation for each product  

### `image_generator.py`
Responsible for:
- Building Gemini prompts  
- Loading reference product images  
- Calling the image model  
- Returning a resized, clean background image  

### `utils.py`
Utility functions for:
- Localization lookup  
- Slug generation  
- Safe-bottom-zone cropping  
- Text wrapping  
- Rendering text overlays  
- Rendering brand logo cards  

### `processor.py`
Coordinates full creative generation:
- Iterates through aspect ratios  
- Calls image generation  
- Applies overlays  
- Integrates Gemini review loop  
- Writes final output files  

### `compliance_and_review.py`
Provides:
- Brand compliance summary  
- Gemini image review (legal, brand, quality)  
- Iterative regeneration via `generate_with_review_loop`  

Gemini review JSON format:
```
legal_compliant: bool
brand_compliant: bool
compliant: bool
quality_score: int
feedback: string
```

---

## 6. Running the Pipeline

### Example — Novatech (default language)
```
python -m creative_pipeline.cli \
  --brief examples/campaign_brief_Novatech.yaml \
  --output output/Novatech_en_US \
  --log campaign_Novatech.log 
```

### Example — TerraQuest Outdoors (Spanish Mexico)
```
python -m creative_pipeline.cli \
  --brief examples/campaign_brief_TerraQuestOutdoors.yaml \
  --output output/old/TerraQuest_ES_MX \
  --log campaign_TerraQuest.log \
  --locale es_MX
```

### Run without log file
```
python -m creative_pipeline.cli \
  --brief examples/campaign_brief_Novatech.yaml \
  --output output/Novatech_quick
```

### Run without any arguments for help
```
python -m creative_pipeline.cli
```

---

## 7. Logs and Troubleshooting

### Log Format
```
YYYY-MM-DD HH:MM:SS,ms LEVEL message
```

### What you will see
- Brief loaded  
- Gemini generation calls  
- Gemini review iteration results  
- Output save paths  

### Common Issues
1. Missing API key  
2. Incorrect YAML paths  
3. Missing logo or reference images  
4. Model review failures → check feedback  

---

## 8. Extending the Pipeline

Ideas for enhancement:
- Adaptive prompt rewriting based on model feedback  
- Per-brand customizable layout templates  
- Support for additional aspect ratios  
- More realistic legal compliance   
- Quality scoring analytics and dashboards  
- Full-stack service

---

## 9. Summary

This project provides:

- AI-driven background creative generation  
- Deterministic, brand-safe overlays  
- Optional compliance + quality control loops  
- Fully modular, easy-to-extend architecture  

It enables scalable and automated production of marketing creatives from structured briefs.

