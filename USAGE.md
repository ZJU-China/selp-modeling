# Usage Guide

## Review the 2KY5 worked example

Open the [2KY5 log directory](methods-and-data/logs/) directly on GitHub. The files are organized by stage:

| Stage | Records |
| --- | --- |
| All-atom preparation | [Seven NAMD preparation logs](methods-and-data/logs/preparation_logs/) |
| All-atom production (TIGER2) | [Four NAMD logs and four exchange histories](methods-and-data/logs/production_logs/) |
| Coarse-grained box preparation | [Chain packing](methods-and-data/logs/packing.log) and [energy minimization](methods-and-data/logs/em_bounded.log) |
| Network sampling | GROMACS output for the 4 ns endpoint segments of [branch A](methods-and-data/logs/A_4000_mdrun.out), [branch B](methods-and-data/logs/B_4000_mdrun.out), and [branch C](methods-and-data/logs/C_4000_mdrun.out) |
| Sampling checks | [Thermodynamics and crosslink-distance XVG files](methods-and-data/logs/sampling/) for the 500 ps segments from 2 to 4 ns |

GitHub can show the text logs directly. Open the raw file to download it. The public copies use generic host addresses and local paths where applicable.

Each TIGER2 production log and exchange history reaches step 25,005,000 (100.02 ns at 4 fs). The replica 3 log records the final output writes and ends before NAMD's usual end-of-program line. Each exchange history has 1,667 entries. The full production logs are about 22 MB each. Open the raw text for [replica 0](https://raw.githubusercontent.com/ZJU-China/selp-modeling/main/methods-and-data/logs/production_logs/replica-0.log), [replica 1](https://raw.githubusercontent.com/ZJU-China/selp-modeling/main/methods-and-data/logs/production_logs/replica-1.log), [replica 2](https://raw.githubusercontent.com/ZJU-China/selp-modeling/main/methods-and-data/logs/production_logs/replica-2.log), [replica 3](https://raw.githubusercontent.com/ZJU-China/selp-modeling/main/methods-and-data/logs/production_logs/replica-3.log).

## Preview the method page

With Python 3 installed, run this command from the repository root:

```bash
python3 -m http.server 8000 --bind 127.0.0.1 --directory methods-and-data
```

Open [http://127.0.0.1:8000/](http://127.0.0.1:8000/). The page walks through sequence preparation, all-atom sampling, coarse-graining, box setup, crosslinking, network relaxation, and elastic modulus calculation. The [protocol directory](methods-and-data/protocols/) contains the corresponding scripts and configurations.

## Work with the monitoring platform

The [monitoring platform](monitoring-platform/) groups the following components.

- [platform-source/frontend/](monitoring-platform/platform-source/frontend/) contains the frontend. Run `npm ci` and `npm run dev` from that directory to start its development server.
- [platform-source/backend/](monitoring-platform/platform-source/backend/) contains the API and workflow services. [flows-app/](monitoring-platform/flows-app/) contains a snapshot of the deployed flow interface.
- [figure-service/](monitoring-platform/figure-service/) contains the figure rendering code. Configure local task data paths in `tasks.json` before using the service.
- [deployment/](monitoring-platform/deployment/) contains configuration examples. Adjust file paths, service accounts, and listener addresses for your environment.

The static preview requires no simulation software. Running the modeling workflows requires the appropriate scientific tools, compatible input structures and force-field files, and locally configured task paths. The public review files include 2KY5 logs as their only run data.
