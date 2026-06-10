"""governance/scriptural_registry.py — Machine-readable scriptural governance categories.

Maps the 11 constitutional categories to their source scriptures, severity levels,
gate actions, and constitutional binding status. This is the authoritative source
registry that feeds the scriptural classifier and constitutional gate.

11 categories, 7 source families:
  Categories: harm_prevention, false_witness, theft_or_fraud, oppression_or_exploitation,
              corruption_or_defilement, mercy_required, justice_required, obedience_required,
              owner_review_required, doctrine_conflict, allowed

  Source families: torah, prophets, writings, gospels, apostolic_writings, apocrypha, whole_canon

Constitutional binding: if True, NO deployment owner can override the gate_action.
  Only the Creator Sovereign may amend constitutionally-bound categories (and must
  authenticate as such — see creator_sovereign.py).

ML classifier mapping: maps existing ml_safety_classifier.py harm categories to the
  scriptural category that best captures the governing principle. The ML signal is
  advisory; the scriptural category is authoritative for the gate action.
"""
from __future__ import annotations

from typing import Dict, List, Tuple

# ── Source family registry ─────────────────────────────────────────────────────

SOURCE_FAMILIES: Dict[str, Dict[str, str]] = {
    "torah": {
        "name": "Torah (Law)",
        "description": "Genesis, Exodus, Leviticus, Numbers, Deuteronomy — foundational law and commandments.",
    },
    "prophets": {
        "name": "Prophets (Nevi'im / Major and Minor Prophets)",
        "description": "Isaiah, Jeremiah, Ezekiel, Daniel, the twelve minor prophets — proclamation and moral authority.",
    },
    "writings": {
        "name": "Writings (Ketuvim / Wisdom literature)",
        "description": "Psalms, Proverbs, Ecclesiastes, Job, Song of Solomon — wisdom, justice, and instruction.",
    },
    "gospels": {
        "name": "Gospels (New Testament)",
        "description": "Matthew, Mark, Luke, John — teachings and authority of Jesus Christ.",
    },
    "apostolic_writings": {
        "name": "Apostolic Writings (Epistles / Acts / Revelation)",
        "description": "Acts, Romans, Corinthians, Galatians, Ephesians, Philippians, Colossians, Thessalonians, "
                       "Timothy, Titus, Philemon, Hebrews, James, Peter, John (epistles), Jude, Revelation.",
    },
    "apocrypha": {
        "name": "Apocrypha / Deuterocanonical Writings",
        "description": "Wisdom of Solomon, Sirach (Ecclesiasticus), Tobit, Judith, Maccabees, Baruch, "
                       "additions to Daniel and Esther — wisdom and moral instruction tradition.",
    },
    "whole_canon": {
        "name": "Whole Canon (cross-testament)",
        "description": "Principles attested across multiple testament traditions.",
    },
}

# ── Severity levels ────────────────────────────────────────────────────────────

SEVERITY_ABSOLUTE = "ABSOLUTE"
SEVERITY_HIGH = "HIGH"
SEVERITY_MEDIUM = "MEDIUM"
SEVERITY_LOW = "LOW"

# ── Gate actions ───────────────────────────────────────────────────────────────

GATE_HARD_STOP = "hard_stop"             # Deny immediately, no further evaluation
GATE_DENY_CONSTITUTIONAL = "deny_constitutional"  # Deny — deployment owner cannot override
GATE_REQUIRE_REVIEW = "require_review"   # Escalate to creator or human review
GATE_ALLOW_WITH_RECORD = "allow_with_record"  # Allow but log under governance
GATE_ALLOW = "allow"                     # Allow — no restriction

# ── Scriptural category registry ──────────────────────────────────────────────

SCRIPTURAL_REGISTRY: Dict[str, Dict] = {

    "harm_prevention": {
        "id": "SCRIP-001",
        "name": "Harm Prevention",
        "description": (
            "Prohibition against doing harm to persons, including physical violence, "
            "weapons construction, self-harm, and mass casualty assistance. "
            "Rooted in the commandment 'thou shalt not kill' (Ex 20:13) and the "
            "apostolic principle of love as the fulfillment of law (Rom 13:10)."
        ),
        "severity": SEVERITY_ABSOLUTE,
        "gate_action": GATE_HARD_STOP,
        "constitutional_binding": True,
        "source_family": "whole_canon",
        "source_references": [
            "Exodus 20:13",       # Thou shalt not kill
            "Deuteronomy 5:17",   # Thou shalt not kill (Deuteronomy repeating)
            "Proverbs 3:29",      # Devise not evil against thy neighbour
            "Matthew 5:21-22",    # You have heard it was said... but I say
            "Romans 13:10",       # Love worketh no ill to his neighbour
            "Sirach 34:21-22",    # Apocrypha: depriving someone of livelihood = shedding blood
        ],
        "ml_category_mapping": ["weapons", "self_harm", "violence"],
    },

    "false_witness": {
        "id": "SCRIP-002",
        "name": "False Witness and Deception",
        "description": (
            "Prohibition against bearing false witness, lying, and deception. "
            "Encompasses manipulation, fraud, false narratives, impersonation, "
            "and unauthorized identity claims. Rooted in the ninth commandment."
        ),
        "severity": SEVERITY_ABSOLUTE,
        "gate_action": GATE_HARD_STOP,
        "constitutional_binding": True,
        "source_family": "whole_canon",
        "source_references": [
            "Exodus 20:16",        # Thou shalt not bear false witness
            "Deuteronomy 5:20",    # Neither shalt thou bear false witness
            "Proverbs 12:22",      # Lying lips are abomination to the LORD
            "Proverbs 19:5",       # A false witness shall not be unpunished
            "John 8:44",           # The devil is a liar and the father of it
            "Revelation 21:8",     # All liars shall have their part in the lake of fire
            "Wisdom 1:11",         # Apocrypha: beware of a deceitful mouth
        ],
        "ml_category_mapping": ["manipulation", "jailbreak"],
    },

    "theft_or_fraud": {
        "id": "SCRIP-003",
        "name": "Theft and Fraud",
        "description": (
            "Prohibition against theft, fraud, counterfeiting, unauthorized access, "
            "money laundering, and taking what belongs to another. "
            "Rooted in the eighth commandment."
        ),
        "severity": SEVERITY_HIGH,
        "gate_action": GATE_DENY_CONSTITUTIONAL,
        "constitutional_binding": True,
        "source_family": "whole_canon",
        "source_references": [
            "Exodus 20:15",        # Thou shalt not steal
            "Leviticus 19:11",     # Ye shall not steal, neither deal falsely
            "Proverbs 11:1",       # A false balance is abomination to the LORD
            "Luke 3:14",           # Do violence to no man, neither accuse any falsely
            "Ephesians 4:28",      # Let him that stole steal no more
            "Sirach 5:8",          # Apocrypha: make not thyself dependent on ill-gotten gains
        ],
        "ml_category_mapping": ["illegal"],
    },

    "oppression_or_exploitation": {
        "id": "SCRIP-004",
        "name": "Oppression and Exploitation",
        "description": (
            "Prohibition against exploiting the vulnerable — including child exploitation, "
            "labor exploitation, coercion, and systems of oppression. "
            "CSAM is the clearest violation: absolute prohibition."
        ),
        "severity": SEVERITY_ABSOLUTE,
        "gate_action": GATE_HARD_STOP,
        "constitutional_binding": True,
        "source_family": "whole_canon",
        "source_references": [
            "Exodus 22:22",        # Ye shall not afflict any widow or fatherless child
            "Proverbs 22:22",      # Rob not the poor because he is poor
            "Isaiah 1:17",         # Relieve the oppressed, judge the fatherless, plead for the widow
            "Matthew 18:6",        # Whoso shall offend one of these little ones...
            "Matthew 25:40",       # Inasmuch as ye have done it unto one of the least of these
            "James 1:27",          # Pure religion: visit the fatherless and widows
            "Judith 9:4",          # Apocrypha: God who avengeth the violation of virgins
        ],
        "ml_category_mapping": ["csam"],
    },

    "corruption_or_defilement": {
        "id": "SCRIP-005",
        "name": "Corruption and Defilement",
        "description": (
            "Prohibition against corrupting the model identity, tampering with governance, "
            "defiling the constitutional record, or producing content that defiles the "
            "mind or spirit. Encompasses unauthorized identity mutation, governance bypass, "
            "and spiritual/moral corruption."
        ),
        "severity": SEVERITY_HIGH,
        "gate_action": GATE_DENY_CONSTITUTIONAL,
        "constitutional_binding": True,
        "source_family": "whole_canon",
        "source_references": [
            "Deuteronomy 27:25",   # Cursed be he that taketh reward to slay an innocent person
            "Proverbs 17:15",      # He that justifieth the wicked and condemneth the just are abomination
            "Daniel 1:8",          # Daniel purposed not to defile himself
            "1 Corinthians 3:17",  # If any man defile the temple of God, him shall God destroy
            "2 Peter 2:19",        # While they promise them liberty they themselves are servants of corruption
            "Sirach 10:2",         # Apocrypha: as the judge of the people is himself, so are his officers
        ],
        "ml_category_mapping": ["jailbreak"],
    },

    "mercy_required": {
        "id": "SCRIP-006",
        "name": "Mercy Required",
        "description": (
            "The model must respond with mercy, compassion, and grace to those in "
            "distress, grief, crisis, or need. Mercy overrides rigid denial when the "
            "intent is restoration and not harm. This category gates responses toward "
            "pastoral care rather than refusal."
        ),
        "severity": SEVERITY_MEDIUM,
        "gate_action": GATE_ALLOW_WITH_RECORD,
        "constitutional_binding": False,
        "source_family": "whole_canon",
        "source_references": [
            "Micah 6:8",           # What doth the LORD require: do justly, love mercy, walk humbly
            "Matthew 5:7",         # Blessed are the merciful for they shall obtain mercy
            "Matthew 9:13",        # I will have mercy and not sacrifice
            "Luke 10:37",          # Go and do thou likewise (Good Samaritan)
            "James 2:13",          # Mercy rejoiceth against judgment
            "Wisdom 12:19",        # Apocrypha: the righteous man must be merciful
        ],
        "ml_category_mapping": [],
    },

    "justice_required": {
        "id": "SCRIP-007",
        "name": "Justice Required",
        "description": (
            "The model must uphold justice, refuse to justify wickedness, and not "
            "render assistance that would pervert the course of justice. Justice "
            "requires accurate reporting, truthful testimony, and non-complicity "
            "with oppression."
        ),
        "severity": SEVERITY_HIGH,
        "gate_action": GATE_DENY_CONSTITUTIONAL,
        "constitutional_binding": True,
        "source_family": "whole_canon",
        "source_references": [
            "Leviticus 19:15",     # In righteousness shalt thou judge thy neighbour
            "Psalm 82:3",          # Defend the poor and fatherless, do justice to the afflicted
            "Proverbs 21:15",      # It is joy to the just to do judgment
            "Amos 5:24",           # Let judgment run down as waters and righteousness as mighty stream
            "Isaiah 61:8",         # I the LORD love judgment, I hate robbery for burnt offering
            "Sirach 4:9",          # Apocrypha: deliver him that suffereth wrong from the hand of the oppressor
        ],
        "ml_category_mapping": [],
    },

    "obedience_required": {
        "id": "SCRIP-008",
        "name": "Obedience Required (to Constitutional Authority)",
        "description": (
            "The model must operate within its constitutional boundaries, obey its "
            "governance hierarchy, and not claim or accept authority beyond its scope. "
            "This category governs runtime compliance: the model must not act autonomously "
            "outside authorized capability tiers."
        ),
        "severity": SEVERITY_MEDIUM,
        "gate_action": GATE_ALLOW_WITH_RECORD,
        "constitutional_binding": False,
        "source_family": "whole_canon",
        "source_references": [
            "Proverbs 3:5-6",      # Trust in the LORD with all thine heart, lean not to thine own understanding
            "Romans 13:1",         # Let every soul be subject unto the higher powers
            "Acts 5:29",           # We ought to obey God rather than men (limit: obedience has a ceiling)
            "Hebrews 13:17",       # Obey them that have the rule over you
            "Wisdom 6:4",          # Apocrypha: ye have not kept the law nor walked after the counsel of God
        ],
        "ml_category_mapping": [],
    },

    "owner_review_required": {
        "id": "SCRIP-009",
        "name": "Owner Review Required",
        "description": (
            "The request falls within a grey area that requires human review before "
            "the model acts. Typically: requests that are borderline harmful, "
            "capability-tier escalation requests, requests that touch the model's "
            "own governance or identity, or requests the model cannot evaluate alone."
        ),
        "severity": SEVERITY_MEDIUM,
        "gate_action": GATE_REQUIRE_REVIEW,
        "constitutional_binding": False,
        "source_family": "writings",
        "source_references": [
            "Proverbs 11:14",      # Where no counsel is the people fall; in multitude of counsellors there is safety
            "Proverbs 15:22",      # Without counsel purposes are disappointed, in multitude of counsellors they are established
            "Ecclesiastes 4:13",   # Better is a poor and wise child than an old and foolish king
        ],
        "ml_category_mapping": [],
    },

    "doctrine_conflict": {
        "id": "SCRIP-010",
        "name": "Doctrine Conflict",
        "description": (
            "The request conflicts with the model's founding doctrine (ADR-0001, ADR-0002, "
            "canonical base doctrine) or with the Tokenless constitutional identity. "
            "Examples: requests to introduce persona taxonomy, rename the identity, "
            "promote unauthorized weights, or modify the cognitive architecture without "
            "creator-sovereign authority."
        ),
        "severity": SEVERITY_HIGH,
        "gate_action": GATE_DENY_CONSTITUTIONAL,
        "constitutional_binding": True,
        "source_family": "apostolic_writings",
        "source_references": [
            "Galatians 1:8",       # Though we or an angel from heaven preach any other gospel...
            "2 Timothy 3:16-17",   # All scripture is profitable for doctrine, for reproof
            "Titus 1:9",           # Holding fast the faithful word as he hath been taught
            "Revelation 22:18-19", # If any man add unto these things / if any man take away
        ],
        "ml_category_mapping": [],
    },

    "allowed": {
        "id": "SCRIP-011",
        "name": "Allowed",
        "description": (
            "The request is within lawful operating boundaries. The model may proceed "
            "according to its capabilities and the applicable capability tier for this "
            "deployment context."
        ),
        "severity": SEVERITY_LOW,
        "gate_action": GATE_ALLOW,
        "constitutional_binding": False,
        "source_family": "whole_canon",
        "source_references": [
            "1 Corinthians 10:23", # All things are lawful for me, but not all things are expedient
            "Romans 14:5",         # Let every man be fully persuaded in his own mind
        ],
        "ml_category_mapping": ["benign"],
    },
}


# ── Lookup helpers ─────────────────────────────────────────────────────────────

def get_category(category_id: str) -> Dict | None:
    """Return a category dict by string ID (e.g. 'harm_prevention')."""
    return SCRIPTURAL_REGISTRY.get(category_id)


def get_by_scrip_id(scrip_id: str) -> Tuple[str, Dict] | None:
    """Return (category_key, category_dict) by SCRIP-NNN id."""
    for k, v in SCRIPTURAL_REGISTRY.items():
        if v["id"] == scrip_id:
            return k, v
    return None


def get_by_ml_category(ml_cat: str) -> List[str]:
    """Return list of scriptural category keys that map from the given ML category."""
    return [k for k, v in SCRIPTURAL_REGISTRY.items() if ml_cat in v.get("ml_category_mapping", [])]


def get_gate_action(category_id: str) -> str:
    """Return the gate_action for a category, or GATE_ALLOW if not found."""
    cat = SCRIPTURAL_REGISTRY.get(category_id)
    return cat["gate_action"] if cat else GATE_ALLOW


def is_constitutionally_bound(category_id: str) -> bool:
    """Return True if this category cannot be overridden by a deployment owner."""
    cat = SCRIPTURAL_REGISTRY.get(category_id)
    return bool(cat and cat.get("constitutional_binding", False))


def constitutionally_bound_categories() -> List[str]:
    """Return all category keys that are constitutionally bound (no deployment-owner override)."""
    return [k for k, v in SCRIPTURAL_REGISTRY.items() if v.get("constitutional_binding", False)]


def verify_registry() -> bool:
    """Structural integrity check — all required fields present, severity/action values valid."""
    required_fields = {"id", "name", "description", "severity", "gate_action",
                       "constitutional_binding", "source_family", "source_references",
                       "ml_category_mapping"}
    valid_severities = {SEVERITY_ABSOLUTE, SEVERITY_HIGH, SEVERITY_MEDIUM, SEVERITY_LOW}
    valid_actions = {GATE_HARD_STOP, GATE_DENY_CONSTITUTIONAL, GATE_REQUIRE_REVIEW,
                     GATE_ALLOW_WITH_RECORD, GATE_ALLOW}
    valid_source_families = set(SOURCE_FAMILIES.keys())

    for key, cat in SCRIPTURAL_REGISTRY.items():
        missing = required_fields - set(cat.keys())
        assert not missing, f"{key}: missing fields {missing}"
        assert cat["severity"] in valid_severities, f"{key}: invalid severity {cat['severity']}"
        assert cat["gate_action"] in valid_actions, f"{key}: invalid gate_action {cat['gate_action']}"
        assert cat["source_family"] in valid_source_families, \
            f"{key}: invalid source_family {cat['source_family']}"
        assert isinstance(cat["source_references"], list) and cat["source_references"], \
            f"{key}: source_references must be a non-empty list"

    return True
