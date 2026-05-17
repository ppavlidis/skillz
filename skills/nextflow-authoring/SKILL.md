---
name: nextflow-authoring
description: >
  Write, structure, and debug Nextflow DSL2 workflows and modules. Covers
  canonical project layout (nf-core conventions), process authoring (input/output
  declarations, container/conda directives, label-based resource management,
  publishDir, errorStrategy), channel operators for bioinformatics (groupTuple,
  join, branch, splitCsv, scatter-gather patterns), the nf-core module format,
  subworkflow composition, automatic parallelization mechanics and what breaks
  it, the config hierarchy with profiles and dynamic resource caps, nf-test
  authoring with stubs and snapshots, and the nf-schema v2 samplesheet pattern.
  Use this skill when authoring or debugging Nextflow DSL2 code — creating
  pipelines from scratch, writing reusable modules, porting DSL1 to DSL2,
  optimizing parallelization, or setting up nf-test. Distinct from the
  nextflow-development skill (which runs nf-core pipelines on existing data).
---

# nextflow-authoring

Write Nextflow DSL2 workflows that are correct, reproducible, and well-structured.
This skill covers the conventions and patterns used in production bioinformatics
pipelines, grounded in nf-core standards and the Nextflow 24.x/25.x documentation.

## When to invoke

Trigger this skill for any request about *writing* Nextflow code:

- "Write a Nextflow pipeline that..."
- "Create a module for [tool]"
- "How do I parallelize this in Nextflow?"
- "Why is my `groupTuple` hanging?"
- "Port this DSL1 workflow to DSL2"
- "Set up nf-test for my module"
- "Why are my channels not joining correctly?"
- "How do I handle optional inputs?"
- "Create a subworkflow that..."
- "How do I configure SLURM/AWS/local profiles?"
- Any `.nf` file authoring, debugging, or review

Do NOT use this skill for running existing nf-core pipelines on data — use the
`nextflow-development` skill for that.

---

## Project layout

Canonical DSL2 structure (nf-core conventions; adoptable even in non-nf-core pipelines):

```
my-pipeline/
├── main.nf                     # Thin entry point — imports + calls workflow
├── nextflow.config             # Params defaults, profiles, plugin declarations
├── nextflow_schema.json        # JSON Schema for params (nf-schema; optional but recommended)
├── assets/
│   ├── schema_input.json       # JSON Schema for samplesheet validation
│   └── NO_FILE                 # Sentinel for optional path inputs (empty file)
├── bin/                        # Custom scripts — automatically on PATH inside every task
├── conf/
│   ├── base.config             # Label → resource mapping (cpus/memory/time per label)
│   ├── modules.config          # Per-process ext.args, ext.prefix, publishDir settings
│   └── igenomes.config         # Reference genome paths (optional)
├── modules/
│   ├── local/                  # Project-specific modules
│   │   └── mytool/main.nf
│   └── nf-core/                # Remote modules (managed by nf-core/tools)
│       └── fastqc/main.nf
├── subworkflows/
│   ├── local/
│   └── nf-core/
├── workflows/
│   └── myanalysis.nf           # Named workflow(s); main.nf delegates here
└── docs/
```

`main.nf` should be 10-20 lines — only includes and an entry `workflow {}` block.
Logic lives in `workflows/`. Modules under `modules/local/` are one process per file.

---

## Process authoring

### Input/output declaration

Use `tuple val(meta), path(files)` as the universal bioinformatics pattern.
The `meta` map carries sample metadata without expanding the channel schema:

```groovy
process FASTP {
    tag "$meta.id"
    label 'process_medium'

    input:
    tuple val(meta), path(reads)
    path  adapter_fasta          // optional — pass NO_FILE sentinel when absent

    output:
    tuple val(meta), path("${prefix}.{fastq.gz,json,html}"), emit: reads
    path  "versions.yml",                                     emit: versions

    script:
    def args   = task.ext.args   ?: ''
    def prefix = task.ext.prefix ?: "${meta.id}"
    def single = meta.single_end  ? "-r1 $reads" : "-i ${reads[0]} -I ${reads[1]}"
    """
    fastp $args $single -o ${prefix}.fastq.gz 2> ${prefix}.json

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        fastp: \$(fastp --version 2>&1 | head -n1 | sed 's/fastp //')
    END_VERSIONS
    """

    stub:
    def prefix = task.ext.prefix ?: "${meta.id}"
    """
    touch ${prefix}.fastq.gz ${prefix}.json ${prefix}.html
    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        fastp: 0.0.0
    END_VERSIONS
    """
}
```

**Input qualifiers:**

| qualifier | use |
|-----------|-----|
| `val(x)` | any Groovy value; stays in memory, not staged to work dir |
| `path(x)` | stages file(s) into task work dir; supports globs; `stageAs: 'name.bam'` to rename |
| `tuple val(...), path(...)` | groups related data; first element is the key in `groupTuple` |
| `env(VAR)` | inject a shell environment variable |
| `stdin` | pipe channel content to process stdin |
| `each val(x)` | cross-product — repeats process for every value; can explode task count |

**Output qualifiers:**

| qualifier | use |
|-----------|-----|
| `path "*.bam", arity: '1'` | exactly one file; `'0..1'` = optional; `'1..*'` = at least one |
| `optional: true` | absent output is not a fatal error |
| `emit: name` | labels the output for named access via `.out.name` |
| `topic: 'versions'` | emit to a global named topic channel (for version aggregation) |

### Container and conda directives

Always specify both; the active profile selects which one Nextflow uses:

```groovy
conda "${moduleDir}/environment.yml"
container "${ workflow.containerEngine == 'singularity' && !task.ext.singularity_pull_docker_container ?
    'https://depot.galaxyproject.org/singularity/fastqc:0.12.1--hdfd78af_0' :
    'biocontainers/fastqc:0.12.1--hdfd78af_0' }"
```

Rules:
- Pin exact versions in both (`fastqc:0.12.1`, never `fastqc:latest`)
- With Wave (`wave.enabled = true`), Nextflow synthesizes containers from conda directives on-the-fly — useful for cloud where conda isn't available natively

### Label system for resource management

Label processes in the process body:

```groovy
process BWAMEM2_MEM {
    label 'process_high'
    ...
}
```

Map labels to resources in `conf/base.config`. Standard nf-core labels:

```groovy
process {
    withLabel: process_single {
        cpus   = { 1 }
        memory = { 6.GB  * task.attempt }
        time   = { 4.h   * task.attempt }
    }
    withLabel: process_low {
        cpus   = { 2     * task.attempt }
        memory = { 12.GB * task.attempt }
        time   = { 4.h   * task.attempt }
    }
    withLabel: process_medium {
        cpus   = { 6     * task.attempt }
        memory = { 36.GB * task.attempt }
        time   = { 8.h   * task.attempt }
    }
    withLabel: process_high {
        cpus   = { 12    * task.attempt }
        memory = { 72.GB * task.attempt }
        time   = { 16.h  * task.attempt }
    }
    withLabel: process_long {
        time   = { 20.h  * task.attempt }
    }
    withLabel: process_high_memory {
        memory = { 200.GB * task.attempt }
    }
    // Hard cap (v24.04.0+) — replaces old check_max() Groovy function
    resourceLimits = [cpus: 32, memory: 512.GB, time: 168.h]
}
```

Config selector priority (lowest → highest):
1. Unscoped process settings
2. Directives in process definition body
3. `withLabel` selectors
4. `withName` by name, then by alias, then fully-qualified (`WORKFLOW:SUB:PROCESS`)

### publishDir conventions

```groovy
publishDir [
    path: { "${params.outdir}/fastp/${meta.id}" },
    mode: params.publish_dir_mode,   // 'copy' | 'symlink' | 'link' | 'move'
    saveAs: { filename -> filename.equals('versions.yml') ? null : filename },
    pattern: "*.{fastq.gz,json,html}"
]
```

Best practice (nf-core): keep `publishDir` out of module `main.nf`; declare it in
`conf/modules.config` via `withName`. This keeps modules portable:

```groovy
// conf/modules.config
process {
    withName: 'MYWORKFLOW:FASTP' {
        publishDir = [
            [path: "${params.outdir}/fastp", mode: params.publish_dir_mode, pattern: "*.json"],
            [path: "${params.outdir}/fastp", mode: params.publish_dir_mode, pattern: "*.html"]
        ]
        ext.args = '--trim_poly_x --detect_adapter_for_pe'
    }
}
```

Use `mode: 'copy'` on clusters/cloud (avoids broken symlinks). As of v24.04.0,
`failOnError: true` is the default — publishing failures abort the pipeline.

### errorStrategy patterns

```groovy
// conf/base.config — applies globally
process {
    errorStrategy = { task.exitStatus in ((130..145) + 104) ? 'retry' : 'finish' }
    maxRetries    = 2
}
```

| strategy | behavior |
|----------|----------|
| `'terminate'` | default; abort pipeline immediately on first failure |
| `'finish'` | let running tasks complete, then abort |
| `'ignore'` | log error, continue; downstream gets no input from failed task |
| `'retry'` | re-queue; combine with `maxRetries` and memory scaling |

Exit codes 137/139 = OOM kill; 143 = SIGTERM timeout — always retry these.
Dynamic exponential memory scaling:

```groovy
errorStrategy = { task.exitStatus in [104, 134, 137, 139, 143, 247] ? 'retry' : 'finish' }
memory        = { 8.GB * (2 ** (task.attempt - 1)) }   // 8 → 16 → 32 GB
```

---

## Channel operators

### Factory methods

```groovy
Channel.of(1, 2, 3)                          // emit literal values; ranges: Channel.of(1..22)
Channel.value('GRCh38')                      // value channel: consumed unlimited times
Channel.fromPath('data/*.fastq.gz', checkIfExists: true)
Channel.fromList(list)                        // emit each list element
Channel.empty()                              // produces nothing; useful for optional branches
Channel.topic('versions')                    // receive all topic emissions globally
```

**Queue vs value channel:** Queue channels are consumed once; value channels are
consumed unlimited times. A `Channel.value()` used in a process input is applied
to every task; a queue channel can only wire to one downstream process or operator.

### Transformation

```groovy
ch.map    { meta, bam -> [meta, bam, bam + '.bai'] }
ch.filter { meta, bam -> meta.type == 'tumor' }
ch.flatMap { meta, files -> files.collect { f -> [meta, f] } }   // one item → many
ch.flatten()          // recursively flatten nested lists
ch.view { "DEBUG: $it" }                     // print and pass through; essential for debugging
ch.ifEmpty(['default'])                      // substitute if channel is empty
ch.first()                                   // take only first emission → value channel
ch.collect()                                 // gather all into one list (closes channel first)
ch.toList()                                  // alias for collect()
```

### Grouping and joining

```groovy
// groupTuple: collect items sharing the same key
// WARNING: without size:, hangs if a group never fills (sample dropped upstream)
ch.groupTuple(by: [0])                      // [ meta, [bam1, bam2, bam3] ]
ch.groupTuple(by: [0], size: 3)             // fires exactly when 3 items with same key arrive

// join: inner join on key (like SQL JOIN)
ch_bam.join(ch_bai, by: [0])               // [ meta, bam, bai ] — drops unmatched
ch_bam.join(ch_bai, by: [0], remainder: true)  // left outer join — keeps unmatched with null

// combine: cartesian product
ch_samples.combine(ch_references)           // every sample × every reference
ch_samples.combine(ch_references, by: 0)   // combine within same key

// transpose: inverse of groupTuple — unzip lists
// [ meta, [bam1, bam2] ] → [ meta, bam1 ], [ meta, bam2 ]
ch.transpose()
```

### Routing and merging

```groovy
// branch: route to named sub-channels
ch.branch { meta, reads ->
    single: meta.single_end
    paired: !meta.single_end
}
// → ch.single, ch.paired

// mix: merge channels (non-deterministic order)
ch1.mix(ch2, ch3)

// concat: sequential merge (ch1 completes before ch2 starts)
ch1.concat(ch2)

// multiMap: emit to multiple named outputs simultaneously
ch.multiMap { meta, bam ->
    bam: [meta, bam]
    meta: meta
}
// → ch.bam, ch.meta
```

### Text / CSV

```groovy
Channel.fromPath('samples.csv')
    .splitCsv(header: true, sep: ',')
    .map { row -> [ [id: row.sample], file(row.fastq) ] }

file('big.fa').splitFasta(by: 1000, file: true)   // split FASTA into chunks
```

---

## Module system

### nf-core module format (canonical reusable module)

One process per file. Required files in `modules/nf-core/<tool>/<subtool>/`:

- `main.nf` — single process definition (template below)
- `meta.yml` — describes inputs/outputs, tool info, authors
- `environment.yml` — conda environment
- `tests/main.nf.test` — nf-test tests
- `tests/main.nf.test.snap` — snapshot file

**`main.nf` template:**

```groovy
process TOOL_SUBTOOL {
    tag "$meta.id"
    label 'process_medium'

    conda "${moduleDir}/environment.yml"
    container "${ workflow.containerEngine == 'singularity' && !task.ext.singularity_pull_docker_container ?
        'https://depot.galaxyproject.org/singularity/tool:1.0.0--h1234_0' :
        'biocontainers/tool:1.0.0--h1234_0' }"

    input:
    tuple val(meta), path(bam), path(bai)
    path  fasta

    output:
    tuple val(meta), path("*.vcf.gz"),     emit: vcf
    tuple val(meta), path("*.vcf.gz.tbi"), emit: tbi
    path  "versions.yml",                  emit: versions

    when:
    task.ext.when == null || task.ext.when      // allows conditional skip via config

    script:
    def args   = task.ext.args   ?: ''
    def prefix = task.ext.prefix ?: "${meta.id}"
    if (!task.memory) error "Process '${task.process}' requires the 'process_medium' label"
    """
    tool subcmd \\
        --threads $task.cpus \\
        $args \\
        $bam > ${prefix}.vcf.gz

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        tool: \$(tool --version 2>&1 | sed 's/tool v//')
    END_VERSIONS
    """

    stub:
    def prefix = task.ext.prefix ?: "${meta.id}"
    """
    echo "" | gzip > ${prefix}.vcf.gz
    touch ${prefix}.vcf.gz.tbi

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        tool: 0.0.0
    END_VERSIONS
    """
}
```

**Module authoring rules:**
- `task.ext.args` — all optional tool arguments; set per-module in `conf/modules.config`
- `task.ext.prefix ?: "${meta.id}"` — always allow output prefix override
- `task.ext.when == null || task.ext.when` — allows conditional skip without touching code
- No hardcoded `params` references inside modules (makes them non-portable)
- No custom `meta` keys in the module body — keep `meta` opaque; pass extras via `task.ext.args`
- `stub:` block is mandatory — `touch` for plain files; `echo "" | gzip >` for `.gz`
- Emit `versions.yml` from every process

### Includes and aliases

```groovy
// Single include
include { FASTQC } from './modules/nf-core/fastqc/main'

// Multiple from same file
include { PROCESS_A; PROCESS_B } from './modules/local/shared'

// Aliasing — use same module twice with different names
include { BWAMEM2_MEM as BWAMEM2_REF   } from './modules/nf-core/bwamem2/mem/main'
include { BWAMEM2_MEM as BWAMEM2_SPIKE } from './modules/nf-core/bwamem2/mem/main'
```

### Installing remote modules

```bash
nf-core modules install fastqc
nf-core modules update fastqc
nf-core subworkflows install bam_sort_stats_samtools
```

---

## Workflow composition

### Named workflow pattern

```groovy
// main.nf — entry workflow
include { MYPIPELINE } from './workflows/mypipeline'
include { samplesheetToList } from 'plugin/nf-schema'

workflow {
    ch_input = Channel.fromList(
        samplesheetToList(params.input, "${projectDir}/assets/schema_input.json")
    )
    MYPIPELINE(ch_input)
}
```

```groovy
// workflows/mypipeline.nf — named workflow
include { FASTQC            } from '../modules/nf-core/fastqc/main'
include { FASTP             } from '../modules/nf-core/fastp/main'
include { BWAMEM2_MEM       } from '../modules/nf-core/bwamem2/mem/main'
include { PREPARE_GENOME    } from '../subworkflows/local/prepare_genome/main'

workflow MYPIPELINE {
    take:
    ch_samplesheet   // channel: [ val(meta), path(reads) ]

    main:
    ch_versions = Channel.empty()

    FASTQC(ch_samplesheet)
    ch_versions = ch_versions.mix(FASTQC.out.versions)

    FASTP(ch_samplesheet, [], false, false, false)
    ch_versions = ch_versions.mix(FASTP.out.versions)

    PREPARE_GENOME()
    BWAMEM2_MEM(FASTP.out.reads, PREPARE_GENOME.out.index, true)
    ch_versions = ch_versions.mix(BWAMEM2_MEM.out.versions)

    emit:
    bam      = BWAMEM2_MEM.out.bam
    versions = ch_versions
}
```

### Subworkflows

```groovy
// subworkflows/local/prepare_genome/main.nf
workflow PREPARE_GENOME {
    take:
    fasta

    main:
    BWAMEM2_BUILD(fasta)
    SAMTOOLS_FAIDX(fasta, [[:], []])

    emit:
    index   = BWAMEM2_BUILD.out.index
    fai     = SAMTOOLS_FAIDX.out.fai
    versions = BWAMEM2_BUILD.out.versions.mix(SAMTOOLS_FAIDX.out.versions)
}
```

### Pipe and and operators

```groovy
// Sequential pipe
Channel.fromPath('data/*.fq') | FASTQC | MULTIQC

// Fan-out same channel to two processes simultaneously
Channel.fromPath('data/*.fq') | (FASTQC & FASTP)
```

---

## Parallelization

Nextflow parallelizes automatically at two levels:

1. **Process-level**: every process call with a channel input spawns independent tasks — 10 samples → 10 concurrent FASTQC jobs, no code required
2. **Item-level**: items emitted by a channel are processed as they arrive; earlier samples don't wait for later ones

### What breaks automatic parallelism

| problem | symptom | fix |
|---------|---------|-----|
| `collect()` without intent | all upstream tasks must finish before process fires | only use `collect()` where fan-in is semantically needed |
| `groupTuple()` without `size:` | pipeline hangs if any sample is dropped upstream | always use `size: N` when group sizes are known; `groupTuple(by:[0], size: params.n_replicates)` |
| Queue channel consumed twice | second consumer sees empty channel silently | assign to named var then use `multiMap`/`branch` for fan-out |
| `first()` on async channel | downstream gets only one item | only use when a single representative value is truly wanted |
| `Channel.value()` + queue `join` | unexpected cartesian product | understand the difference before mixing them |

### `maxForks` directive

Limits concurrent instances of a specific process — use for rate-limited APIs or license-limited tools:

```groovy
process LICENSED_TOOL {
    maxForks 4
    ...
}
```

---

## Config system

### Config hierarchy (lowest → highest priority)

1. `$HOME/.nextflow/config`
2. `nextflow.config` in project dir
3. `nextflow.config` in launch dir (if different)
4. `-c extra.config` on command line
5. `-C only.config` — uses *only* this file, ignores all others

### `nextflow.config` structure

```groovy
plugins {
    id 'nf-schema@2.1.0'    // always pin plugin versions
    id 'nf-wave@1.0.0'
}

params {
    input            = null
    outdir           = './results'
    genome           = null
    publish_dir_mode = 'copy'
    max_cpus         = 16
    max_memory       = '128.GB'
    max_time         = '240.h'
}

includeConfig 'conf/base.config'
includeConfig 'conf/modules.config'

docker {
    enabled    = true
    runOptions = '-u $(id -u):$(id -g)'
}

profiles {
    local {
        process.executor = 'local'
    }
    slurm {
        process.executor        = 'slurm'
        process.queue           = 'normal'
        clusterOptions          = '--account=myproject'
        executor.queueSize      = 200
        executor.submitRateLimit = '10/1sec'
        singularity.enabled     = true
        singularity.autoMounts  = true
    }
    aws {
        process.executor = 'awsbatch'
        process.queue    = 'my-queue'
        aws.region       = 'us-east-1'
        wave.enabled     = true
        fusion.enabled   = true
    }
    conda {
        conda.enabled  = true
        docker.enabled = false
    }
    test {
        params.input   = "${projectDir}/assets/test_samplesheet.csv"
        params.outdir  = '/tmp/test_results'
        process.resourceLimits = [cpus: 2, memory: '6.GB', time: '30.m']
    }
}
```

**Critical config rules:**
- Declare `params` blocks before `includeConfig` — params declared after an include are NOT visible to the included file
- Never set `process.cpus` globally without labels — loses per-process granularity
- Always set `singularity.autoMounts = true` on HPC — otherwise bind mounts for reference data are absent
- Use `scratch true` in process scope on shared NFS clusters to reduce staging traffic

---

## Testing with nf-test

### Module test file

```groovy
// modules/nf-core/fastqc/tests/main.nf.test
nextflow_process {
    name "Test FASTQC"
    script "../main.nf"
    process "FASTQC"

    test("paired-end reads") {
        when {
            process {
                """
                input[0] = [
                    [ id:'test', single_end:false ],
                    [ file(params.modules_testdata_base_path + 'genomics/sarscov2/illumina/fastq/test_1.fastq.gz'),
                      file(params.modules_testdata_base_path + 'genomics/sarscov2/illumina/fastq/test_2.fastq.gz') ]
                ]
                """
            }
        }
        then {
            assert process.success
            assert process.out.html.size() == 1
            assert process.out.zip.size()  == 1
            assert snapshot(process.out.html, process.out.zip).match()
        }
    }

    test("stub") {
        options "-stub"
        when {
            process {
                """
                input[0] = [ [ id:'test' ], [] ]
                """
            }
        }
        then {
            assert process.success
        }
    }
}
```

**Key assertions:**
- `process.success` — task exited 0
- `process.out.channel.size()` — number of emissions
- `snapshot(process.out.html).match()` — snapshot test; stored in `.snap`; fails if output changes
- `path(process.out.results[0][1]).md5` — checksum assertion
- `process.trace` — access resource usage

Run: `nf-test test modules/nf-core/fastqc/tests/main.nf.test`

### Stub runs

Run with `nextflow run main.nf -stub` to skip real execution and validate channel wiring
and file staging. Requires a `stub:` block in every process. Essential for iteration.

---

## Common patterns

### Samplesheet → channel (nf-schema v2)

Requires `plugins { id 'nf-schema@2.1.0' }` in `nextflow.config`:

```groovy
include { samplesheetToList } from 'plugin/nf-schema'

workflow {
    Channel.fromList(
        samplesheetToList(params.input, "${projectDir}/assets/schema_input.json")
    )
}
```

`assets/schema_input.json` is a JSON Schema draft-07 file that validates columns,
types, required fields, and enum values. The plugin supports CSV, TSV, JSON, YAML
samplesheets. Output is `[ val(meta), path(fastq_1), path(fastq_2) ]` per row.

### Scatter-gather (fan-out / fan-in)

```groovy
// Scatter: one input → many chunks
process SPLIT_FASTA {
    input:  path big_fasta
    output: path "chunk_*.fa"      // glob emits multiple files as separate items
    script: "seqkit split2 -n 100 $big_fasta"
}

ch_chunks = SPLIT_FASTA.out.flatten()   // flatten glob → individual channel items
PROCESS_CHUNK(ch_chunks)                // runs in parallel per chunk

// Gather: collect all chunks and merge
MERGE_RESULTS(PROCESS_CHUNK.out.results.collect())
```

### Join-based fan-in (re-pairing after divergence)

```groovy
ch_bam = ALIGN.out.bam          // [ meta, bam ]
ch_bai = INDEX.out.bai          // [ meta, bai ]

ch_bam
    .join(ch_bai, by: [0])      // [ meta, bam, bai ]
    | CALL_VARIANTS
```

### Optional inputs (NO_FILE sentinel)

```groovy
// main.nf
ch_dbsnp = params.dbsnp ?
    Channel.fromPath(params.dbsnp, checkIfExists: true) :
    Channel.value(file("${projectDir}/assets/NO_FILE"))

// process
process GATK_HC {
    input:
    tuple val(meta), path(bam)
    path  dbsnp

    script:
    def known = dbsnp.name != 'NO_FILE' ? "--known-sites $dbsnp" : ""
    """
    gatk HaplotypeCaller $known -I $bam ...
    """
}
```

### Group samples by condition, then process jointly

```groovy
ch_bam
    .map    { meta, bam, bai -> [ meta.condition, meta, bam, bai ] }
    .groupTuple(by: 0)
    .map    { condition, metas, bams, bais ->
        [ [id: condition], bams, bais ]
    }
    | JOINT_GENOTYPE
```

### Version aggregation (topic channels — v24+)

```groovy
// Each process emits: path "versions.yml", emit: versions, topic: versions

// In the workflow — collect globally without explicit channel wiring:
Channel.topic('versions')
    .collectFile(name: 'collated_versions.yml')
    | CUSTOM_DUMPSOFTWAREVERSIONS
```

The older approach (still dominant): collect `versions` output from each process:
```groovy
ch_versions = Channel.empty()
ch_versions = ch_versions.mix(FASTQC.out.versions)
ch_versions = ch_versions.mix(FASTP.out.versions)
CUSTOM_DUMPSOFTWAREVERSIONS(ch_versions.collect())
```

---

## Latest features (Nextflow 24.x / 25.x)

| feature | version | what it does |
|---------|---------|-------------|
| `resourceLimits` | 24.04.0 | native per-task resource cap; replaces `check_max()` Groovy function |
| `publishDir failOnError: true` | 24.04.0 | publishing failures abort pipeline by default |
| Topic channels | 24.04.0 | `Channel.topic('x')` + `topic: 'x'` output qualifier for global fan-in |
| `outputDir` global config | 24.10.0 | sets default output directory globally |
| Wave container provisioning | 24.x | builds containers from conda directives on-the-fly; enables cloud-native execution |
| nf-schema v2 | 24.x | `samplesheetToList` replaces `fromSamplesheet`; multi-format + JSON Schema validation |
| Strict syntax mode | 25.04+ | `addParams` / `params` in includes removed; `when:` section deprecated |
| Fusion filesystem | 24.x | S3/GCS mounted as POSIX in tasks; eliminates staging latency on cloud |
| Seqera Platform integration | 24.x | run monitoring, resource optimization, data studios |
| Typed processes (preview) | 26.04 | `nextflow.enable.types` — not yet production-stable |

---

## Anti-patterns

### Breaking parallelism
- **`collect()` everywhere** — serializes the pipeline; use only where fan-in is semantically correct
- **`groupTuple()` without `size:`** — hangs if any sample is dropped upstream
- **Consuming queue channel twice** — second consumer is silently empty; use `multiMap`/`branch`
- **`first()` on an async channel** — downstream sees only one item; converts queue to value

### Reproducibility failures
- **Unpinned container tags** — `bwa:latest` drifts silently; always pin exact versions
- **No version emission** — can't reconstruct what ran after the fact
- **Writing to `params.outdir` directly from process scripts** — bypasses Nextflow's output tracking; use `publishDir`
- **Absolute paths in process scripts** — breaks portability across machines
- **Modifying input files in-place** — inputs are staged as links; some executors stage read-only

### Configuration pitfalls
- **`params` after `includeConfig`** — params not visible to the included file
- **`process.cpus` set globally without labels** — loses per-process granularity
- **No `-profile`** — runs local config on HPC; tasks aren't submitted to the scheduler
- **Missing `singularity.autoMounts = true`** — reference data bind mounts absent on HPC
- **No `executor.queueSize` or `submitRateLimit`** — floods scheduler on large jobs

### Module authoring mistakes
- **Hardcoded tool args in script block** — use `task.ext.args` instead; makes modules non-configurable
- **Hardcoded output prefix** — use `task.ext.prefix ?: "${meta.id}"`; filename collisions when aliasing
- **Custom `meta` keys in module body** — breaks nf-core portability; pass extras via `task.ext.args`
- **No `stub:` block** — prevents `-stub` dry runs from validating workflow structure
- **`when:` section** — deprecated; use `task.ext.when == null || task.ext.when`
- **`params` used directly inside modules** — hard to test in isolation; pass via inputs

### Channel operator traps
- **`join()` drops non-matching items by default** — use `remainder: true` for outer join when one-sided data expected
- **`groupTuple()` on complex tuples without `by:`** — uses first element by default; specify explicitly
- **Relying on `mix()` order** — non-deterministic; never use for order-dependent logic
- **`Channel.value()` + queue `join`** — can produce unexpected cartesian products

---

## Reference

- [Nextflow docs](https://www.nextflow.io/docs/latest/) — authoritative source for 25.x
- [Nextflow patterns](https://nextflow-io.github.io/patterns/) — cookbook of common workflow patterns
- [nf-core module guidelines](https://nf-co.re/docs/contributing/modules) — canonical module format
- [nf-schema docs](https://nextflow-io.github.io/nf-schema/) — samplesheet validation + `samplesheetToList`
- [nf-test docs](https://www.nf-test.com/) — test framework for processes and workflows
- Tremblay-Savard et al. (2021) — nf-core community standards for bioinformatics pipelines
