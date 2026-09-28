# Elden Ring Boss Combat Statistics Dataset

## Overview
This dataset contains cleaned and structured combat-related statistics for **Elden Ring bosses**, collected from publicly available information on the Fextralife Elden Ring Wiki and processed into a consistent tabular format.

The goal of this dataset is to support:
- Game balance analysis
- Difficulty modeling and boss comparison
- Machine learning projects (e.g., boss recommendation systems)
- Exploratory data analysis by the Elden Ring community

The dataset is intentionally **raw-but-clean**: values are normalized where possible, but no model-specific preprocessing (imputation, scaling, or labeling) has been applied.

---

## Dataset Summary
- **Rows:** 142 bosses
- **Columns:** ~30–35 (depending on optional feature drops)
- **Granularity:** One row per boss
- **Format:** CSV

Each row represents a single boss encounter as documented on the wiki.

---

## Column Groups and Descriptions

### Core Identifiers
| Column | Description |
|------|-------------|
| `boss` | Canonical boss name |

---

### Health
| Column | Description |
|------|-------------|
| `health_total` | Total HP of the boss (sum of all phases, if applicable) |
| `health_phase1` | Phase 1 HP (NaN for single-phase bosses) |
| `health_phase2` | Phase 2 HP (NaN for single-phase bosses) |

Notes:
- Multi-phase bosses (e.g., Malenia, Radagon) have phase-wise values.
- Single-phase bosses correctly contain NaN for phase columns.

---

### Defensive Stats
| Column | Description |
|------|-------------|
| `defense` | Defense value if explicitly listed on the wiki |
| `stance` | Stance (poise) value required to stagger the boss |
| `parryable` | Whether the boss can be parried (1 = yes, 0 = no) |

Missing values indicate that the stat is not published, not zero.

---

### Damage Types Used by Boss (Binary Flags)
Each column indicates whether the boss uses that damage type.

| Column | Damage Type |
|------|------------|
| `dmg_standard` | Standard / physical damage |
| `dmg_slash` | Slash damage |
| `dmg_strike` | Strike damage |
| `dmg_pierce` | Pierce damage |
| `dmg_magic` | Magic damage |
| `dmg_fire` | Fire damage |
| `dmg_lightning` | Lightning damage |
| `dmg_holy` | Holy damage |

Values:
- `1` → Boss uses this damage type
- `0` → Boss does not use this damage type

---

### Status Effect Inflictions (Binary Flags)
These columns indicate whether the boss can inflict a given status effect.

| Column | Status Effect |
|------|---------------|
| `inflicts_scarlet_rot` | Scarlet Rot |
| `inflicts_bleed` | Hemorrhage (Bleed) |
| `inflicts_poison` | Poison |
| `inflicts_frostbite` | Frostbite |

Values:
- `1` → Boss can inflict this status
- `0` → Boss does not inflict this status

---

### Status Resistances (First Proc Only)
These columns represent the buildup required to trigger a status effect **for the first time**.

| Column | Description |
|------|-------------|
| `res_poison_first` | Poison resistance (first proc) |
| `res_scarlet_rot_first` | Scarlet Rot resistance (first proc) |
| `res_hemorrhage_first` | Bleed resistance (first proc) |
| `res_frostbite_first` | Frostbite resistance (first proc) |

Notes:
- Higher values indicate greater resistance.
- Missing values indicate resistance not explicitly listed on the wiki.

---

### Informational Text Columns
| Column | Description |
|------|-------------|
| `inflicts` | Raw text description of inflicted statuses (human-readable) |

This column is included for reference and documentation purposes. It is not intended for direct use in machine learning models.

---

## Missing Values Policy
Missing values (`NaN`) appear intentionally and reflect **absence of published data**, not data collection errors.

Examples:
- Single-phase bosses do not have `health_phase2`
- Many bosses do not publish defense values
- Some resistances are not documented and therefore missing

Users are encouraged to handle missing values according to their analytical or modeling needs.

---

## Data Source
- Primary source: **Fextralife Elden Ring Wiki**
- Data collected via automated scraping and manual validation
- This dataset is unofficial and not affiliated with FromSoftware or Bandai Namco

---

## Intended Use Cases
- Boss difficulty modeling
- Player build recommendation systems
- Comparative analysis of boss mechanics
- Educational machine learning projects

---

## Limitations
- Stats reflect wiki documentation, not in-game datamining
- Some bosses lack complete information
- Difficulty is not directly labeled and must be derived

---

## License and Attribution
This dataset is provided for **educational and research purposes**.

If you use this dataset in a project or publication, please credit:
> "Data sourced from Fextralife Elden Ring Wiki and compiled into a structured dataset by the author."

---

## Contact / Project Context
This dataset was created as part of an ML project exploring boss difficulty and recommendation systems in Elden Ring.

Suggestions, issues, and improvements are welcome.