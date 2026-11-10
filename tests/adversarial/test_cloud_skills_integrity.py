"""
Adversarial and Empirical Verification Test Suite for Cloud AI Trading Skills.

Tests the installation, integrity, YAML frontmatter syntax, metadata accuracy,
instruction body depth, reference preservation, and mirror consistency between
.agents/skills and .agent/skills.
"""

import hashlib
import os
from pathlib import Path
import re
import sys
import pytest
import yaml

WORKSPACE_ROOT = Path(r"c:\Users\AmirM\Documents\Agentic trading")
CATALOG_DIRS = [
    WORKSPACE_ROOT / ".agents" / "skills",
    WORKSPACE_ROOT / ".agent" / "skills",
]

ACCEPTED_SKILLS = [
    "agency-sre-site-reliability-engineer",
    "agency-devops-automator",
    "agency-incident-response-commander",
    "agency-autonomous-optimization-architect",
    "agency-secrets-credential-hygiene-engineer",
    "agency-cloud-security-architect",
    "agency-finops-engineer",
    "agency-api-tester",
    "agency-performance-benchmarker",
    "agency-realtime-collaboration-engineer",
    "docker-containerization",
    "observability-sre",
]

# Note: The actual files as defined in SKILL.md and source repo are:
# patterns.md, sharp_edges.md, validations.md (plural)
SKILLS_WITH_REFERENCES = {
    "docker-containerization": ["patterns.md", "sharp_edges.md", "validations.md"],
    "observability-sre": ["patterns.md", "sharp_edges.md", "validations.md"],
}


def parse_frontmatter_and_body(skill_path: Path):
    """
    Strictly parses YAML frontmatter enclosed by '---' and returns (frontmatter_dict, body_str).
    Raises ValueError or yaml.YAMLError on failure.
    """
    content = skill_path.read_text(encoding="utf-8")
    lines = content.splitlines(keepends=True)

    if not lines or lines[0].strip() != "---":
        raise ValueError(f"{skill_path}: Missing starting '---' YAML delimiter on line 1")

    # Find closing delimiter
    closing_idx = -1
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            closing_idx = i
            break

    if closing_idx == -1:
        raise ValueError(f"{skill_path}: Missing closing '---' YAML delimiter")

    yaml_block = "".join(lines[1:closing_idx])
    body_str = "".join(lines[closing_idx + 1:])

    # Strict parse
    metadata = yaml.safe_load(yaml_block)
    if not isinstance(metadata, dict):
        raise ValueError(f"{skill_path}: Frontmatter did not parse into a mapping/dict, got {type(metadata)}")

    return metadata, body_str


def get_file_hash(path: Path) -> str:
    hasher = hashlib.sha256()
    hasher.update(path.read_bytes())
    return hasher.hexdigest()


class TestCloudSkillsEmpiricalIntegrity:
    """Empirical verification test suite for all 12 cloud skills across both catalogs."""

    @pytest.mark.parametrize("catalog_dir", CATALOG_DIRS)
    def test_catalog_directory_exists_and_total_count(self, catalog_dir):
        """Verify the catalog directory exists and has 30 skill folders."""
        assert catalog_dir.exists(), f"Directory does not exist: {catalog_dir}"
        subdirs = [p for p in catalog_dir.iterdir() if p.is_dir()]
        assert len(subdirs) == 31, (
            f"Catalog {catalog_dir} expected 31 skill subdirectories, but found {len(subdirs)}"
        )

    @pytest.mark.parametrize("skill_name", ACCEPTED_SKILLS)
    @pytest.mark.parametrize("catalog_dir", CATALOG_DIRS)
    def test_skill_manifest_exists(self, catalog_dir, skill_name):
        """Verify SKILL.md exists and is non-empty for every skill in both catalogs."""
        skill_dir = catalog_dir / skill_name
        manifest = skill_dir / "SKILL.md"
        assert skill_dir.is_dir(), f"Skill directory missing: {skill_dir}"
        assert manifest.is_file(), f"SKILL.md missing: {manifest}"
        assert manifest.stat().st_size > 0, f"SKILL.md is empty: {manifest}"

    @pytest.mark.parametrize("skill_name", ACCEPTED_SKILLS)
    @pytest.mark.parametrize("catalog_dir", CATALOG_DIRS)
    def test_skill_yaml_frontmatter_strict(self, catalog_dir, skill_name):
        """
        Strictly parses YAML frontmatter:
        - name matches directory name
        - description is non-empty, string, >= 20 characters
        """
        manifest = catalog_dir / skill_name / "SKILL.md"
        metadata, _ = parse_frontmatter_and_body(manifest)

        assert "name" in metadata, f"{manifest} frontmatter missing 'name'"
        assert metadata["name"] == skill_name, (
            f"{manifest}: 'name' ({metadata['name']}) does not match directory ({skill_name})"
        )

        assert "description" in metadata, f"{manifest} frontmatter missing 'description'"
        desc = metadata["description"]
        assert isinstance(desc, str), f"{manifest}: 'description' is not string: {type(desc)}"
        assert len(desc.strip()) >= 20, (
            f"{manifest}: 'description' is too short ({len(desc.strip())} chars): {desc}"
        )

    @pytest.mark.parametrize("skill_name", ACCEPTED_SKILLS)
    @pytest.mark.parametrize("catalog_dir", CATALOG_DIRS)
    def test_skill_body_depth(self, catalog_dir, skill_name):
        """Verify that markdown body contains actionable instructions > 500 bytes."""
        manifest = catalog_dir / skill_name / "SKILL.md"
        _, body = parse_frontmatter_and_body(manifest)
        body_bytes = len(body.encode("utf-8"))
        assert body_bytes > 500, (
            f"{manifest}: Body content has {body_bytes} bytes, expected > 500 bytes"
        )
        assert "#" in body, f"{manifest}: Body contains no markdown headings"

    @pytest.mark.parametrize("skill_name,expected_files", SKILLS_WITH_REFERENCES.items())
    @pytest.mark.parametrize("catalog_dir", CATALOG_DIRS)
    def test_skill_references_exist_and_readable(self, catalog_dir, skill_name, expected_files):
        """Verify that skills with references have all required markdown files, non-empty and readable."""
        ref_dir = catalog_dir / skill_name / "references"
        assert ref_dir.is_dir(), f"References directory missing: {ref_dir}"

        for ref_file in expected_files:
            file_path = ref_dir / ref_file
            assert file_path.is_file(), f"Reference file missing: {file_path}"
            size = file_path.stat().st_size
            assert size > 100, f"Reference file {file_path} is unexpectedly small ({size} bytes)"
            content = file_path.read_text(encoding="utf-8")
            assert len(content.strip()) > 50, f"Reference file {file_path} content is too short"

    @pytest.mark.parametrize("skill_name", ACCEPTED_SKILLS)
    def test_catalog_mirror_parity(self, skill_name):
        """Verify that .agents/skills and .agent/skills have byte-for-byte identical SKILL.md manifests."""
        dir1 = CATALOG_DIRS[0] / skill_name
        dir2 = CATALOG_DIRS[1] / skill_name

        manifest1 = dir1 / "SKILL.md"
        manifest2 = dir2 / "SKILL.md"

        hash1 = get_file_hash(manifest1)
        hash2 = get_file_hash(manifest2)
        assert hash1 == hash2, (
            f"Parity mismatch for {skill_name}: {manifest1} ({hash1}) != {manifest2} ({hash2})"
        )

        # Check references if any
        if skill_name in SKILLS_WITH_REFERENCES:
            for ref_file in SKILLS_WITH_REFERENCES[skill_name]:
                rf1 = dir1 / "references" / ref_file
                rf2 = dir2 / "references" / ref_file
                assert get_file_hash(rf1) == get_file_hash(rf2), (
                    f"Reference parity mismatch for {skill_name}/{ref_file}"
                )

    @pytest.mark.parametrize("catalog_dir", CATALOG_DIRS)
    def test_catalog_readme_indexes_all_accepted_skills(self, catalog_dir):
        """Verify that README.md exists and mentions each of the 12 accepted skills."""
        readme = catalog_dir / "README.md"
        assert readme.is_file(), f"Catalog README missing: {readme}"
        text = readme.read_text(encoding="utf-8")
        assert len(text.strip()) > 500, f"README too short ({len(text.strip())} chars)"

        missing = []
        for sk in ACCEPTED_SKILLS:
            if sk not in text:
                missing.append(sk)
        assert not missing, f"Catalog README {readme} is missing references to skills: {missing}"


def run_standalone_verification():
    """Runs all checks imperatively and prints formatted tables and metrics."""
    print("=" * 80)
    print("EMPIRICAL CHALLENGER VERIFICATION HARNESS: CLOUD AI TRADING SKILLS")
    print("=" * 80)

    total_checks = 0
    passed_checks = 0
    failed_checks = 0
    failures = []

    def check(desc, assertion_func):
        nonlocal total_checks, passed_checks, failed_checks
        total_checks += 1
        try:
            assertion_func()
            passed_checks += 1
            print(f"  [PASS] {desc}")
        except Exception as e:
            failed_checks += 1
            failures.append((desc, str(e)))
            print(f"  [FAIL] {desc}: {e}")

    # 1. Catalog folder and count checks
    print("\n--- 1. Catalog Folder Checks ---")
    for cat in CATALOG_DIRS:
        def c1(c=cat):
            assert c.exists(), f"Directory missing: {c}"
            subdirs = [p for p in c.iterdir() if p.is_dir()]
            assert len(subdirs) == 30, f"Expected 30 subdirs, got {len(subdirs)}"
        check(f"Directory {cat.relative_to(WORKSPACE_ROOT)} exists with exactly 30 skill folders", c1)

    # 2. Manifest and YAML validation across all 24 skills
    print("\n--- 2. Manifest Existence, YAML Parsing, Name & Description Validation ---")
    for cat in CATALOG_DIRS:
        for sk in ACCEPTED_SKILLS:
            def c2(c=cat, s=sk):
                p = c / s / "SKILL.md"
                assert p.is_file(), f"Manifest file missing: {p}"
                meta, body = parse_frontmatter_and_body(p)
                assert meta.get("name") == s, f"Name mismatch: {meta.get('name')} != {s}"
                assert isinstance(meta.get("description"), str), f"Description is not string"
                assert len(meta.get("description").strip()) >= 20, "Description too short"
                assert len(body.encode("utf-8")) > 500, f"Body too small: {len(body.encode('utf-8'))} bytes"
            check(f"{cat.name}/{sk}: Valid YAML, name match, description, body > 500B", c2)

    # 3. References validation
    print("\n--- 3. References Integrity Validation ---")
    for cat in CATALOG_DIRS:
        for sk, files in SKILLS_WITH_REFERENCES.items():
            for ref_name in files:
                def c3(c=cat, s=sk, r=ref_name):
                    rp = c / s / "references" / r
                    assert rp.is_file(), f"Ref file missing: {rp}"
                    assert rp.stat().st_size > 100, f"Ref file too small: {rp.stat().st_size} bytes"
                    text = rp.read_text(encoding="utf-8")
                    assert len(text.strip()) > 50, f"Ref content too short"
                check(f"{cat.name}/{sk}/references/{ref_name}: File exists, readable, size > 100B", c3)

    # 4. Mirror Parity Check
    print("\n--- 4. Parity Between .agents/skills and .agent/skills ---")
    for sk in ACCEPTED_SKILLS:
        def c4(s=sk):
            m1 = CATALOG_DIRS[0] / s / "SKILL.md"
            m2 = CATALOG_DIRS[1] / s / "SKILL.md"
            h1 = get_file_hash(m1)
            h2 = get_file_hash(m2)
            assert h1 == h2, f"SHA-256 mismatch: {h1} vs {h2}"
            if s in SKILLS_WITH_REFERENCES:
                for rf in SKILLS_WITH_REFERENCES[s]:
                    r1 = CATALOG_DIRS[0] / s / "references" / rf
                    r2 = CATALOG_DIRS[1] / s / "references" / rf
                    assert get_file_hash(r1) == get_file_hash(r2), f"Ref SHA-256 mismatch for {rf}"
        check(f"Byte-for-byte SHA256 parity for {sk} and any references", c4)

    # 5. README Index Check
    print("\n--- 5. Catalog README Indexing ---")
    for cat in CATALOG_DIRS:
        def c5(c=cat):
            readme = c / "README.md"
            assert readme.is_file(), f"Missing README.md in {c}"
            content = readme.read_text(encoding="utf-8")
            for sk in ACCEPTED_SKILLS:
                assert sk in content, f"Skill {sk} not referenced in README"
        check(f"{cat.name}/README.md documents all 12 accepted skills", c5)

    print("\n" + "=" * 80)
    print(f"VERIFICATION RESULTS: {passed_checks}/{total_checks} PASSED (Failed: {failed_checks})")
    print("=" * 80)

    if failures:
        print("\nFAILURES:")
        for desc, err in failures:
            print(f"  - {desc}: {err}")
        return 1
    else:
        print("\nALL EMPIRICAL CHECKS COMPLETED SUCCESSFULLY WITH 0 ERRORS.")
        return 0


if __name__ == "__main__":
    sys.exit(run_standalone_verification())
