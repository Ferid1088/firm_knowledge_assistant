"""
VLM prompts for the Docling + Qwen3-VL ingestion pipeline.

The facility-map prompt (FACILITY_MAP_SYSTEM) is the part that needs the most
tuning — spatial descriptions are where a VLM most easily drifts or
hallucinates. Notes on tuning are at the bottom of this file.

All prompts ask for strict JSON so the output drops straight into a chunk.
"""

# --------------------------------------------------------------------------
# 1. Classification — one cheap, short call that decides which describer to use
# --------------------------------------------------------------------------

CLASSIFY_SYSTEM = """You are a document-figure classifier. You are shown a single
figure cropped from a business or technical document. Respond with ONLY a JSON
object, no prose, no markdown fences.

Choose exactly one value for "figure_type" from this list:
- "floor_plan"        : interior layout of rooms on a single floor
- "site_plan"         : outdoor/property layout, grounds, parking, buildings from above
- "evacuation_plan"   : escape-route / fire-safety map (Flucht- und Rettungsplan)
- "electrical_schematic": wiring, circuit, single-line electrical diagram
- "utility_map"        : piping, HVAC, network, or other facility-utility routing
- "chart"             : bar/line/pie chart or other data plot
- "diagram"           : flowchart, org chart, or conceptual diagram
- "table_image"       : a table that was captured as an image
- "photo"             : a photograph of a real scene or object
- "logo"              : a logo, stamp, or decorative mark with no informational content
- "other"

The first five values are "spatial maps" and trigger detailed spatial description.

Output schema:
{"figure_type": "<one value>", "is_spatial_map": <true|false>, "confidence": <0.0-1.0>}
"""

CLASSIFY_USER = "Classify this figure."


# --------------------------------------------------------------------------
# 2. Facility-map description — the centerpiece. Used for any "spatial map".
# --------------------------------------------------------------------------

FACILITY_MAP_SYSTEM = """You are an expert at reading facility maps: floor plans,
site plans, evacuation plans, electrical schematics, and utility/HVAC maps. Your
job is to convert ONE map image into a precise, searchable text record that a
retrieval system can use to answer questions like "where is the main electrical
panel on floor 2?" or "Wo ist der nächste Notausgang vom Lagerraum?".

Hard rules:
1. TRANSCRIBE ALL VISIBLE TEXT EXACTLY, in its original language. Room numbers,
   labels, codes, and legends are exactly what users search for. Keep German
   terms verbatim (e.g. "Notausgang", "Hauptschalter", "Lagerraum", "EG/1.OG").
   Do not translate, do not normalize, do not correct spelling.
2. NEVER INVENT. If a label, symbol, or location is unreadable or ambiguous, say
   so in "unreadable_notes". An honest gap is far more valuable than a guess.
3. Use RELATIVE / DIRECTIONAL language for positions ("north-east corner",
   "left of the main entrance", "between Room 204 and the stairwell"). If a north
   arrow or orientation marker is present, anchor directions to it; otherwise
   describe positions relative to other labeled elements, not to absolute compass
   points.
4. Be exhaustive about SAFETY and UTILITY features: exits, emergency exits,
   stairs, elevators, fire extinguishers, fire alarms, first-aid points,
   assembly points, electrical panels, main shutoffs, water/gas valves, server
   rooms. These are the highest-value retrieval targets.

Respond with ONLY a JSON object (no markdown fences) using this schema:
{
  "map_kind": "floor_plan | site_plan | evacuation_plan | electrical_schematic | utility_map | other",
  "facility_or_title": "<title or best description of what facility/area this is, or null>",
  "floor_or_area": "<floor/level/section identifier if shown, e.g. '2. OG', else null>",
  "orientation": "<how directions are anchored, e.g. 'north arrow points up', else null>",
  "scale": "<scale if printed, e.g. '1:100', else null>",
  "legend": [{"symbol": "<symbol/color/icon described>", "meaning": "<verbatim label>"}],
  "zones": [
    {
      "label": "<verbatim room/area name>",
      "identifier": "<verbatim number/code if any, else null>",
      "location": "<relative position within the map>",
      "notes": "<purpose or contents if labeled, else null>"
    }
  ],
  "key_features": [
    {"feature": "<e.g. 'Emergency exit', 'Hauptschalter', 'Fire extinguisher'>",
     "location": "<relative position, and which zone it is in or nearest to>"}
  ],
  "connections": ["<e.g. 'Corridor C1 links the lobby to rooms 201-205'>"],
  "all_text": ["<every distinct text string visible on the map, verbatim>"],
  "summary": "<one dense paragraph in the document's primary language describing the map, the major zones, and how they connect — written so it reads well on its own and embeds well>",
  "unreadable_notes": "<anything unclear, occluded, or low-confidence, else null>"
}
"""

# The caption/surrounding text Docling found near the figure is passed in here as
# extra grounding. Helps the model name the facility and floor correctly.
FACILITY_MAP_USER = """Describe this facility map following the schema exactly.

Context found near the figure in the source document (may be empty or partial):
\"\"\"{caption}\"\"\"
"""


# --------------------------------------------------------------------------
# 3. Generic figure description — charts, diagrams, photos, image-tables
# --------------------------------------------------------------------------

GENERIC_FIGURE_SYSTEM = """You convert ONE figure from a document into a searchable
text record. Transcribe all visible text exactly and in its original language.
Never invent values; if something is unreadable, note it.

For charts/tables: capture the data points, axis labels, units, and any totals.
For diagrams: capture nodes, their labels, and the relationships/arrows between them.
For photos: describe the scene and any visible text or signage.

Respond with ONLY a JSON object (no markdown fences):
{
  "title": "<title/caption of the figure, or null>",
  "embedded_text": ["<every distinct text string, verbatim>"],
  "data_or_structure": "<for charts: the numbers/series; for diagrams: nodes and edges; else null>",
  "summary": "<one dense paragraph describing the figure so it reads and embeds well>",
  "unreadable_notes": "<anything unclear, else null>"
}
"""

GENERIC_FIGURE_USER = """Describe this figure following the schema exactly.

Context found near the figure in the source document (may be empty or partial):
\"\"\"{caption}\"\"\"
"""


SPATIAL_MAP_KINDS = {
    "floor_plan",
    "site_plan",
    "evacuation_plan",
    "electrical_schematic",
    "utility_map",
}


# ==========================================================================
# TUNING NOTES for FACILITY_MAP_SYSTEM (this is where reliability is won/lost)
# ==========================================================================
#
# 1. TEMPERATURE: run map description at temperature <= 0.1. Spatial reasoning
#    is where sampling noise turns into hallucinated rooms. Keep it near-greedy.
#
# 2. RESOLUTION: maps are dense. Feed the crop at high resolution. With Qwen3-VL,
#    raise the per-image pixel budget rather than letting it downscale — set
#    images_scale=2.0 (or higher) in Docling so the crop is large, and do not
#    cap image tokens too aggressively in vLLM. A downscaled floor plan loses
#    exactly the small room numbers users search for.
#
# 3. LARGE MAPS — TILE THEM: a single A1 site plan exceeds what any VLM reads
#    reliably in one shot. If the crop is very large (e.g. > ~2000px on a side),
#    split it into overlapping tiles (~20% overlap), describe each tile, then do
#    a second "merge" call that fuses the tile JSONs into one record. The overlap
#    lets the model keep features that straddle a tile boundary.
#
# 4. GROUNDING WITH CAPTION: always pass the Docling caption / nearby text into
#    {caption}. It is how the model reliably fills facility_or_title and
#    floor_or_area instead of guessing.
#
# 5. GERMAN OUTPUT: the schema says "primary language" for the summary. For your
#    DE customers, the summary should come back in German so it matches German
#    queries at retrieval time. The verbatim fields (all_text, labels) are always
#    kept in the original language regardless.
#
# 6. EVAL: build a tiny golden set (10-20 real maps) where you hand-label the
#    must-find features (every exit, every panel). Score the pipeline on recall
#    of those features, not on text similarity. That is the metric your customers
#    actually feel. Wire it into your existing Ragas/Langfuse setup.
