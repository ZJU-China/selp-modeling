# Usage Guide

## Review the 2KY5 worked example

Open the [2KY5 log directory](website/2KY5/logs/) directly on GitHub. The files are organized by stage:

| Stage | Records |
| --- | --- |
| All-atom preparation | [Seven NAMD preparation logs](website/2KY5/logs/preparation_logs/) |
| Coarse-grained box preparation | [Chain packing](website/2KY5/logs/packing.log) and [energy minimization](website/2KY5/logs/em_bounded.log) |
| Network sampling | GROMACS output for the 4 ns endpoint segments of [branch A](website/2KY5/logs/A_4000_mdrun.out), [branch B](website/2KY5/logs/B_4000_mdrun.out), and [branch C](website/2KY5/logs/C_4000_mdrun.out) |
| Sampling checks | [Thermodynamics and crosslink-distance XVG files](website/2KY5/logs/sampling/) for the 500 ps segments from 2 to 4 ns |

GitHub can show the text logs directly. Open the raw file to download it. The public copies use generic host addresses and local paths where applicable.

## Preview the method page

With Python 3 installed, run this command from the repository root:

```bash
python3 -m http.server 8000 --bind 127.0.0.1 --directory website
```

Open [http://127.0.0.1:8000/](http://127.0.0.1:8000/). The page walks through sequence preparation, all-atom sampling, coarse-graining, box setup, crosslinking, network relaxation, and elastic modulus calculation. The [protocol directory](website/2KY5/) contains the corresponding scripts and configurations.

## Work with the platform source

- [platform-source/frontend/](platform-source/frontend/) contains the frontend. Run `npm ci` and `npm run dev` from that directory to start its development server.
- [platform-source/backend/](platform-source/backend/) contains the API and workflow services. [flows-app/](flows-app/) contains a snapshot of the deployed flow interface.
- [figure-service/](figure-service/) contains the figure rendering code. Configure local task data paths in `tasks.json` before using the service.
- [deployment/](deployment/) contains configuration examples. Adjust file paths, service accounts, and listener addresses for your environment.

The static preview requires no simulation software. Running the modeling workflows requires the appropriate scientific tools, compatible input structures and force-field files, and locally configured task paths. The public review files include 2KY5 logs as their only run data.
