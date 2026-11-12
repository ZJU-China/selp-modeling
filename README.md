# ZJU-China | SELP Hydrogel Modeling

This repository accompanies ZJU-China’s iGEM project. It contains the source code for the silk–elastin-like polypeptide (SELP) hydrogel modeling workflow, the web interface, and the 2KY5 simulation logs used as the worked example.

The workflow starts from a protein sequence, samples single-chain conformations with TIGER2, coarse-grains a representative structure with Martini 3, constructs and relaxes a crosslinked network, and calculates its axial small-strain modulus.

| Resource | What you will find |
| --- | --- |
| [Usage guide](USAGE.md) | How to review the method and preview the website |
| [2KY5 simulation logs](website/ky5/logs/) | All-atom preparation, packing, minimization, and A/B/C network sampling |
| [2KY5 protocols and configurations](website/ky5/) | NAMD and GROMACS inputs, network construction, and static analysis scripts |
| [Platform source](platform-source/) | Frontend, backend, and modeling tools |
| [Figure service](figure-service/) | Source code for rendering plots from locally configured task data |

[SHA256_manifest.json](SHA256_manifest.json) records the checksums of the files in this snapshot.
