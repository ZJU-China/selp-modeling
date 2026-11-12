# ZJU-China | SELP Hydrogel Modeling

This repository accompanies ZJU-China’s iGEM project. It contains the source code for the silk–elastin-like polypeptide (SELP) hydrogel modeling workflow, the web interface, and the 2KY5 simulation logs used as the worked example.

The workflow starts from a protein sequence, samples single-chain conformations with TIGER2, coarse-grains a representative structure with Martini 3, constructs and relaxes a crosslinked network, and calculates its axial small-strain modulus.

| Resource | What you will find |
| --- | --- |
| [Usage guide](USAGE.md) | How to review the method and preview the website |
| [Modeling Methods and Data](methods-and-data/) | Step-by-step method page and 2KY5 files |
| [2KY5 simulation logs](methods-and-data/logs/) | All-atom preparation and TIGER2 production, packing, minimization, and A/B/C network sampling |
| [2KY5 protocols and configurations](methods-and-data/protocols/) | NAMD and GROMACS inputs, network construction, and static analysis scripts |
| [Monitoring platform](monitoring-platform/) | FAMD monitoring, workflow interface, figure service, and deployment configuration |
| [Platform source](monitoring-platform/platform-source/) | Frontend, backend, and modeling tools |
| [Figure service](monitoring-platform/figure-service/) | Source code for rendering plots from locally configured task data |

[SHA256_manifest.json](SHA256_manifest.json) records the checksums of the files in this snapshot.
