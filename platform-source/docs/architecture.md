

# Software Architecture & System Diagrams

MD platform — architecture — architecture
overview, data-flow schematics, and component dependency maps.

All diagrams use [Mermaid](https://mermaid.js.org/) syntax (mindmap, flowchart,
sequence diagram). Render with any Mermaid-compatible viewer (VS Code preview,
GitHub, GitLab, etc.).

---

## 1. System Overview

```mermaid
mindmap
  root((MD Platform))
    Frontend
      React + TypeScript
      Vite dev server :5173
      NGL.js 3D viewer
      Molstar structure viewer
      Recharts plots
      Xterm.js terminal
    Backend
      Node.js + Express :3001
      SSH session pool
      SWR cache layer
      JSON persistence
    Remote Servers
      iGEM Server
        127.0.0.1:22
        password auth
      ZJU Remote
        192.0.2.20:20009
        SSH key auth
    Task Types
      tiger2
        NAMD replica exchange
        TIGER2 sampling
      gromacs_cg
        GROMACS coarse-grained
        Martini force field
      seq_to_pdb
        sequence to PDB
        annotation CSV
      tiger2_dcd_to_gromacs_cg_pdb
        DCD to CG input
        MDP template
    Data Flow
      DCD trajectories
      PDB structures
      Convergence analysis
      Cluster analysis
```

---

## 2. Backend Module Architecture

```mermaid
flowchart TB
    subgraph Entry["index.js — entry point"]
        E1[loadTasks]
        E2[loadFlows]
        E3[mountRoutes]
        E4[autoConnect]
    end

    subgraph Routes["routes/ — HTTP API"]
        R1["servers.js — CRUD + connect/disconnect"]
        R2["tasks.js — CRUD + SSH exec + run/pause/continue controls"]
        R3["flows.js — Flow CRUD + POST /:id/start"]
        R4["files.js — remote file browser"]
        R5["data.js — sim-status / structure / cluster / trajectory"]
        R6["transition.js — local task generation"]
        R7["video.js — VMD rendering"]
    end

    subgraph Services["services/ — business logic"]
        S1["ssh.js — SSH session pool + exec/upload/download"]
        S2["transition.js — runTransition (python3 generate.py)"]
        S3["flow-links.js — syncFlowLinks (symlink management)"]
        S4["task-dir.js — scaffoldTaskConfig + dir resolution"]
    end

    subgraph Store["store.js — JSON persistence"]
        ST1[serverStore]
        ST2[taskStore]
        ST3[flowStore]
    end

    subgraph Cache["cache.js — SWR cache"]
        C1[in-memory Map]
        C2[disk persistence]
        C3[warmUp on startup]
    end

    subgraph TaskTypes["tasktype/ — plugin system"]
        T1["tiger2/ — main.py + lib/ + routes/"]
        T2["gromacs_cg/ — main.py + lib/ + routes/"]
        T3["seq_to_pdb/ — generate.py (local)"]
        T4["tiger2_dcd_to_gromacs_cg_pdb/ — generate.py (local)"]
    end

    E1 --> ST2
    E2 --> ST3
    R1 --> S1
    R2 --> S1
    R2 --> S4
    R3 --> S3
    R6 --> S2
    S2 --> T3
    S2 --> T4
    S4 --> T1
    S4 --> T2
    R5 --> C1
    C1 --> C2
    C3 --> C1

    style Entry fill:#e1f5fe
    style Routes fill:#f3e5f5
    style Services fill:#e8f5e8
    style Store fill:#fff3e0
    style Cache fill:#fce4ec
    style TaskTypes fill:#f1f8e9
```

---

## 3. Task Type Plugin System

```mermaid
flowchart LR
    subgraph TaskType["backend/tasktype/<type>/"]
        direction TB
        TC["task_config.template.json"]
        MP["main.py — CLI entry point"]
        LIB["lib/ — task_config.py, ssh_client.py, ..."]
        ROUTES["routes/ — shared route handlers"]
        GEN["generate.py — transition task generator"]

        TC --> MP
        MP --> LIB
        MP --> ROUTES
    end

    subgraph TaskInstance["backend/tasks/<id>/"]
        direction TB
        SC["scripts/task_config.json"]
        INP["input/ — uploaded files"]
        OUT["output/ — generated files"]
        LOG["logs/ — remote log sync"]
        CACHE["cache/ — trajectory data"]

        SC --> MP
        INP --> GEN
        OUT --> GEN
    end

    subgraph Shared["backend/_shared/"]
        SH1["ssh_client.py — SSHClient"]
        SH2["task_config_base.py — BaseTaskConfig"]
        SH3["sequence_annotation.py — motif finder"]
        SH4["routes/ — make_dispatch factory"]
    end

    LIB --> SH1
    LIB --> SH2
    ROUTES --> SH4

    style TaskType fill:#e3f2fd
    style TaskInstance fill:#fce4ec
    style Shared fill:#e8f5e8
```

---

## 4. Flow Pipeline System

```mermaid
flowchart TB
    subgraph Flow["Flow — ordered task chain (flow_* wrapper steps)"]
        direction LR
        F1["flow_tiger2\n— sequence → PDB → NAMD MD\n— DCD → CG start (folded in)"]
        F2["flow_gromacs_cg\n— runs: GROMACS CG simulation"]

        F1 -->|"next: cg_start.pdb, cg_input.mdp"| F2
    end

    subgraph FlowLinks["symlink chain"]
        direction LR
        L1["tasks/F2/input/flow-F1 → F1/output"]
    end

    subgraph StartSequence["POST /api/flows/:id/start"]
        S1["Sort tasks by createdAt"]
        S2["For each task:"]
        S3["transition? → runTransition (local)"]
        S4["compute? → SSH exec (remote)"]
        S5["Wait for completion"]
        S6["Next task in chain"]
    end

    F2 -.-> L1

    S1 --> S2
    S2 --> S3
    S2 --> S4
    S3 --> S5
    S4 --> S5
    S5 --> S6

    style Flow fill:#e1f5fe
    style FlowLinks fill:#f3e5f5
    style StartSequence fill:#e8f5e8
```

---

## 5. Transition Task Data Flow

```mermaid
sequenceDiagram
    participant U as User (Frontend)
    participant API as Backend API
    participant TR as services/transition.js
    participant PY as generate.py
    participant FS as Filesystem

    U->>API: PUT /api/tasks/update (config)
    API->>API: Merge config into taskStore
    API->>FS: saveTasks() → tasks.json

    U->>API: POST /api/transition/generate (taskId)
    API->>TR: runTransition(taskId)
    TR->>FS: Write scripts/task_config.json
    TR->>FS: python3 generate.py --task-id --local-dir --task-config
    FS->>PY: Execute generate.py
    PY->>FS: Read input/ (upstream files via flow link)
    PY->>FS: Write output/ (generated files)
    PY-->>TR: JSON result (files, atoms, notes)
    TR-->>API: { ok, files, notes }
    API-->>U: { ok, files, notes }
```

---

## 6. Task Creation: Template Extraction

```mermaid
sequenceDiagram
    participant U as Frontend
    participant API as POST /api/tasks/create
    participant SD as task-dir.js
    participant TMPL as task_config.template.json
    participant FS as tasks/<id>/scripts/

    U->>API: { name, taskType, serverId, workDir }
    API->>API: Generate task ID
    API->>API: Push to taskStore.tasks
    API->>SD: scaffoldTaskConfig(id, type, overrides)
    SD->>TMPL: Read tasktype/<type>/task_config.template.json
    SD->>TMPL: Parse JSON, extract _comment
    SD->>SD: deepMerge(template, { remoteDir, logPrefix })
    SD->>FS: Write task_config.json (never overwrite)
    SD-->>API: { created, path, usedTemplate }
    API->>API: saveTasks()
    API->>API: syncFlowLinks()
    API-->>U: { ok, task, scaffold }
```

---

## 7. Frontend Component Tree

```mermaid
mindmap
  root((Frontend))
    App
      ThemeProvider
      BrowserRouter
      Layout
        Sidebar
          FlowBar
            FlowCard
              TaskCard
                TransitionForm
                  NGLViewer
                TaskConfigForm
                TaskTerminal
        MainContent
          Pages
            Dashboard
              SimStatsCards
              SimProgress
              TimeEstimate
              TemperatureTrace
              ReplicaStatus
              ConvergenceSection
            Temperature
              TemperaturePage
              ReplicaSummary
              ScheduleConfig
              VisitExchange
            Structure
              TrajectoryTab
                NGLViewer
                SequenceAnnotation
              ReplicaGrid
              RmsdChart
              RgChart
              E2eChart
              SsChart
            Cluster
              ScatterPlot
              ClusterTable
              PiePopulation
            Convergence
              ConvergencePage
              ConvergenceSummary
              ReplicaDetails
              BlockChart
            Files
              FileBrowser
    Components
      RunningTasksBar
      ServerManager
      CreateTaskForm
      VideoExport
```

---

## 8. Data Flow: Simulation → Visualization

```mermaid
flowchart TB
    subgraph Remote["Remote Server"]
        R1["NAMD / GROMACS"]
        R2["DCD trajectory files"]
        R3["PDB structure files"]
        R4["LOG files"]
    end

    subgraph Sync["Data Sync (SSH)"]
        direction LR
        SY1["checkpoint route"]
        SY2["trajectory route"]
        SY3["cluster route"]
        SY4["structure route"]
    end

    subgraph Local["Local Cache"]
        L1["cache/checkpoint_<id>.json"]
        L2["cache/trajectory_<id>.json"]
        L3["cache/cluster_<id>.json"]
        L4["cache/structure_<id>.json"]
        L5["cache/simStatus_<id>.json"]
    end

    subgraph API["API Endpoints"]
        A1["GET /api/data/sim-status/:id"]
        A2["GET /api/data/structure/:id"]
        A3["GET /api/data/cluster/:id"]
        A4["GET /api/data/convergence/:id"]
        A5["GET /api/data/dcd-preview/:filename"]
    end

    subgraph Frontend["Frontend Visualization"]
        V1["SimStatsCards — step, time, energy"]
        V2["NGL.js — 3D structure viewer"]
        V3["ReplicaGrid — multi-frame playback"]
        V4["ScatterPlot — cluster positions"]
        V5["ConvergenceSummary — E2E, Rg plots"]
    end

    R1 --> R2
    R1 --> R3
    R1 --> R4
    R2 --> SY2
    R3 --> SY4
    R4 --> SY1
    SY1 --> L1
    SY2 --> L2
    SY3 --> L3
    SY4 --> L4
    L1 --> A1
    L2 --> A5
    L3 --> A3
    L4 --> A2
    L5 --> A1
    A1 --> V1
    A2 --> V2
    A3 --> V4
    A4 --> V5
    A5 --> V3

    style Remote fill:#ffcdd2
    style Sync fill:#c8e6c9
    style Local fill:#bbdefb
    style API fill:#d1c4e9
    style Frontend fill:#ffe0b2
```

---

## 9. Sequence Annotation System

```mermaid
flowchart TB
    subgraph Input["User Input"]
        I1["input/sequences.csv\nsequence,label,color"]
        I2["config.annotations\nJSON array"]
    end

    subgraph Backend["Backend Processing"]
        B1["sequence_annotation.py\nfind_all_occurrences()"]
        B2["For each sequence motif:\nsliding window over topology"]
        B3["Output: chain, resseq, motif, label, color"]
    end

    subgraph Storage["Data Path"]
        S1["GET /api/data/sequence-annotations/:id"]
        S2["Cache: structure_<id>.json"]
    end

    subgraph Frontend["Frontend Display"]
        F1["NGL.js structure viewer"]
        F2["Residue coloring by motif"]
        F3["Legend panel"]
        F4["Sequence bar (domain map)"]
    end

    I1 --> B1
    I2 --> B1
    B1 --> B2
    B2 --> B3
    B3 --> S1
    S1 --> S2
    S2 --> F1
    F1 --> F2
    F1 --> F3
    F1 --> F4

    style Input fill:#e1f5fe
    style Backend fill:#e8f5e8
    style Storage fill:#fff3e0
    style Frontend fill:#f3e5f5
```

---

## 10. DCD Parser: CHARMM vs NAMD 3 Format

```mermaid
flowchart TB
    subgraph DCDFile["DCD File Structure"]
        direction TB
        H1["CORD magic (4 bytes)"]
        H2["Header: nset, istart, nsavc (80 bytes)"]
        H3["Atom count block: 4 + natoms + 4"]
        F1["Frame data"]
    end

    subgraph Standard["Standard CHARMM DCD"]
        SC1["Single contiguous XYZ block"]
        SC2["sz + X Y Z + sz"]
        SC3["frame_size = 4 + natoms*12 + 4"]
    end

    subgraph NAMD3["NAMD 3 DCD"]
        NC1["4-byte prefix before CORD"]
        NC2["3 separate coordinate blocks"]
        NC3["sz_X + X + sz_X + sz_Y + Y + sz_Y + sz_Z + Z + sz_Z"]
        NC4["frame_size = 3 * (4 + natoms*4 + 4)"]
    end

    subgraph Detection["Format Detection"]
        D1["Read first_sz at frame_start"]
        D2{"first_sz == natoms*4 ?"}
        D3["NAMD 3 (3-block)"]
        D4{"first_sz == natoms*12 ?"}
        D5["Standard (1-block)"]
    end

    H1 --> H2
    H2 --> H3
    H3 --> F1
    F1 --> D1
    D1 --> D2
    D2 -->|yes| D3
    D2 -->|no| D4
    D4 -->|yes| D5

    D3 --> NC1
    NC1 --> NC2
    NC2 --> NC3
    NC3 --> NC4

    D5 --> SC1
    SC1 --> SC2
    SC2 --> SC3

    style DCDFile fill:#e1f5fe
    style Standard fill:#e8f5e8
    style NAMD3 fill:#fff3e0
    style Detection fill:#f3e5f5
```

---

## 11. File System Layout

```mermaid
mindmap
  root((igem-2026-software))
    backend/
      index.js
      store.js
      cache.js
      ssh.js
      sync.js
      tasks.json
      routes/
        servers.js
        tasks.js
        flows.js
        files.js
        data.js
        transition.js
        video.js
      services/
        ssh.js
        transition.js
        flow-links.js
        task-dir.js
      tasktype/
        tiger2/
          main.py
          lib/
          routes/
          task_config.template.json
        gromacs_cg/
          main.py
          lib/
          routes/
          task_config.template.json
        seq_to_pdb/
          generate.py
          task_config.template.json
        tiger2_dcd_to_gromacs_cg_pdb/
          generate.py
          task_config.template.json
      tasks/
        <task-id>/
          scripts/
            task_config.json
          input/
            flow-prevId symlink
          output/
          logs/
          cache/
      _shared/
        ssh_client.py
        task_config_base.py
        sequence_annotation.py
        routes/
    frontend/
      src/
        App.tsx
        types.ts
        api.ts
        components/
          TaskConfig/
          Dashboard/
          Structure/
          Cluster/
          Convergence/
          Temperature/
        lib/
          nglHelpers.ts
    docs/
      architecture.md
      task-creation.md
      feature-gap-analysis.md
      sequence-annotation-workflow.md
```

---

## 12. Key Design Patterns

```mermaid
mindmap
  root((Design Patterns))
    Plugin Architecture
      tasktype/ as plugin tree
      main.py route dispatch
      lib/ for domain logic
      routes/ as thin wrappers
      _shared/ for cross-type code
    SWR Cache
      stale-while-revalidate
      in-memory + disk persistence
      warmUp on startup
      expireCache for soft invalidation
    Flow Pipeline
      tasks ordered by createdAt
      symlinks for file access
      next[] for output-to-input mapping
      POST /:id/start for sequential launch
    Transition Tasks
      local execution (no SSH)
      generate.py CLI scripts
      scaffoldTaskConfig for templates
      task_config.json per task
    SSH Session Pool
      persistent connections
      exec/upload/download
      auto-reconnect on failure
      session caching by serverId
    JSON Persistence
      tasks.json for all task data
      flows.json for flow definitions
      servers.json for server configs
      saveTasks() for atomic writes
```
