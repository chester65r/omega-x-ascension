#!/usr/bin/env python3
"""Designly art-direction preflight adapted from Designly (CC BY 4.0)."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

VAGUE_ADJECTIVES = {
    "premium",
    "modern",
    "bold",
    "cinematic",
    "futuristic",
    "luxury",
    "luxurious",
    "elegant",
    "stunning",
    "beautiful",
    "dynamic",
    "sleek",
    "sophisticated",
    "creative",
    "eye-catching",
    "impactful",
    "epic",
}
DECORATIVE_EFFECTS = {
    "neon",
    "glow",
    "hologram",
    "holographic",
    "particles",
    "chrome",
    "liquid metal",
    "lens flare",
    "cyberpunk",
    "glass",
    "smoke",
    "sparks",
    "floating objects",
    "bokeh",
}


def words(value: str) -> list[str]:
    return re.findall(r"[a-zA-Z-]+", (value or "").lower())


def lint(spec: dict) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []

    def add(severity: str, code: str, message: str) -> None:
        findings.append({"severity": severity, "code": code, "message": message})

    for key in ("intent", "concept", "hierarchy", "composition", "typography", "color", "lighting"):
        if not isinstance(spec.get(key), dict):
            add("critical", "missing-section", f"Required section is absent or invalid: {key}")
    if findings:
        return findings
    intent, concept, hierarchy = spec["intent"], spec["concept"], spec["hierarchy"]
    composition, typography, color = spec["composition"], spec["typography"], spec["color"]
    if not str(intent.get("primary_message", "")).strip():
        add("critical", "missing-primary-message", "The primary communication job is not locked.")
    proposition = str(concept.get("visual_proposition", "")).strip()
    excluded = {
        "and",
        "with",
        "a",
        "an",
        "the",
        "visual",
        "image",
        "design",
        "around",
        "when",
        "into",
        "from",
        "that",
        "this",
        "for",
    }
    meaningful = [
        word for word in words(proposition) if word not in VAGUE_ADJECTIVES and word not in excluded
    ]
    vague = [word for word in words(proposition) if word in VAGUE_ADJECTIVES]
    if not proposition:
        add("critical", "missing-visual-proposition", "The visual proposition is empty.")
    elif len(meaningful) < 5 and len(vague) >= 2:
        add(
            "major",
            "adjective-only-concept",
            "The concept relies on adjectives rather than a visible subject/action.",
        )
    if (
        not str(hierarchy.get("primary", "")).strip()
        or not str(hierarchy.get("one_second_read", "")).strip()
    ):
        add("major", "weak-hierarchy", "Specify a single primary focal event and one-second read.")
    if composition.get("focal_points") != 1:
        add(
            "major",
            "primary-focal-count",
            "Declare exactly one primary focal point per interface state.",
        )
    if not composition.get("grid_type") or not composition.get("alignment_anchors"):
        add("major", "missing-layout-logic", "Declare a grid and alignment anchors.")
    if not str(composition.get("negative_space", "")).strip():
        add("minor", "unassigned-negative-space", "Negative space has no explicit function.")
    if not str(composition.get("crop_logic", "")).strip():
        add("minor", "missing-viewport-behavior", "Responsive viewport behavior is not declared.")
    if not str(composition.get("eye_path", "")).strip():
        add(
            "major",
            "missing-eye-path",
            "The eye path does not connect the focal point to supporting actions.",
        )
    roles = typography.get("roles", []) or []
    if len(roles) > 4:
        add(
            "minor",
            "type-role-proliferation",
            "Use no more than four type roles without a documented exception.",
        )
    if typography.get("class") in {"typography-heavy", "poster-ad-layout"} and not typography.get(
        "exact_copy_locked"
    ):
        add("major", "unlocked-copy", "Typography-heavy layouts must lock exact copy.")
    if typography.get("language_direction") not in {"ltr", "rtl", "mixed", "none"}:
        add("major", "undefined-reading-direction", "Declare the interface reading direction.")
    contrast = str(color.get("contrast_target", ""))
    if "4.5:1" not in contrast or "3:1" not in contrast:
        add(
            "major",
            "missing-contrast-target",
            "Declare WCAG AA contrast targets for normal and large text.",
        )
    effects = spec.get("effects", []) or []
    if any(not str(effect.get("purpose", "")).strip() for effect in effects):
        add(
            "critical",
            "effect-without-job",
            "Every declared effect must have a clear communication or usability purpose.",
        )
    effect_names = " ".join(str(effect.get("name", "")) for effect in effects).lower()
    slop_hits = sorted({term for term in DECORATIVE_EFFECTS if term in effect_names})
    if len(slop_hits) >= 4:
        add(
            "major",
            "decorative-effect-stack",
            "Several common synthetic-effect families are stacked: " + ", ".join(slop_hits),
        )
    if len(spec.get("style_families", []) or []) > 2:
        add(
            "major",
            "style-family-entropy",
            "Keep the design system within two coherent style families.",
        )
    if not (spec.get("restraints", []) or []):
        add("major", "missing-restraints", "Define anti-clutter and capability-honesty restraints.")
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description="Lint an Art Direction Spec before UI execution.")
    parser.add_argument("spec", help="Path to a Designly art-direction JSON file")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()
    data = json.loads(Path(args.spec).read_text(encoding="utf-8"))
    findings = lint(data)
    if args.as_json:
        print(json.dumps(findings, indent=2, ensure_ascii=False))
    elif not findings:
        print("PASS: Designly preflight found no deterministic structural issues")
    else:
        for finding in findings:
            print(f"{finding['severity'].upper()} [{finding['code']}]: {finding['message']}")
    return 1 if any(finding["severity"] in {"critical", "major"} for finding in findings) else 0


if __name__ == "__main__":
    raise SystemExit(main())
