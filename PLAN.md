<USER_REQUEST>
# DocXPilot Activity Signal Analyzer

Overall plan and implementation spec for the DSP Lab project, written to be handed to Gemini Antigravity.

## 1. How to use this document

1. Save this document as `PLAN.md` in the project root (export it as Markdown).
2. Open the project in Antigravity and paste the master prompt below.
3. Work one phase at a time (Section 12). Do not let the agent skip ahead. Every phase has acceptance checks that must pass before moving on.

Master prompt (paste first):

```
You are extending an existing Python CLI project called DocXPilot. Read PLAN.md completely, then read the existing source files listed in Phase 0. Implement ONLY the phase I name. Follow the existing code style: dataclasses in analyzers/models.py, rich for console output, flat imports such as `from analyzers.models import ...`. Do not remove or rewrite existing analyzers. After each phase, run the acceptance checks and report the results. Ask me before adding any dependency that is not listed in PLAN.md.
```

Then say: Implement Phase 0.

## 2. Project summary

DocXPilot is a Typer CLI that scans a codebase with six analyzers (directory, code, git, dependencies, config, existing docs), merges the results into a `ProjectKnowledge` object through `KnowledgeAggregator`, sends that to the Gemini API, and writes generated documentation.

The project requirement is to use deep learning in a DSP lab. Calling Gemini is not enough, because it is an API call to someone else's model and involves no signal processing. This plan adds a seventh analyzer that makes the project a legitimate DSP plus deep learning project.

**The idea:** the git history of a repository is a discrete-time signal. Commits per day and lines changed per day are sampled once per day (fs = 1 sample/day). The analyzer applies classical DSP (detrending, filtering, windowing, FFT, STFT) to find the project's rhythm, then a trained 1D convolutional autoencoder to detect anomalous activity. The findings appear in the generated docs and as plots.

## 3. What the analyzer produces

Input: the same as today, a path to a project folder that contains a `.git` directory. No new input is required.

Output:

- A new section in the generated docs called Project Activity and Health: dominant rhythm, anomalies, inactivity gaps.
- `activity.png`: raw signal, filtered signal, and highlighted anomalies.
- `spectrum.png`: magnitude spectrum with the dominant peak marked.
- `spectrogram.png`: STFT of the commit signal showing how the rhythm changes over time.
- Rich terminal summary, for example:

```
Activity Signal Analysis
  Span: 142 days | Active days: 61 | Commits: 87
  Dominant period: 7.0 days (weekly rhythm), strength 0.34
  Anomalies: 2 burst windows, 1 inactivity gap (23 days)
```

## 4. End-to-end flow

```
docxpilot generate ./some-project
        |
        v
KnowledgeAggregator.aggregate()
  1 Directory analyzer     (existing)
  2 Code analyzer          (existing)
  3 Git analyzer           (existing)
  4 Dependency analyzer    (existing)
  5 Config analyzer        (existing)
  6 Docs reader            (existing)
  7 Activity analyzer      (NEW)
      a. git log --numstat -> daily commit and churn signals
      b. DSP: detrend, low-pass, Hann window, FFT, STFT, features
      c. DL: autoencoder reconstruction error -> burst/rhythm anomalies
      d. Rule: long zero runs -> inactivity gaps
      e. ActivityReport + PNG plots
        |
        v
ProjectKnowledge (now has .activity)
        |
        v
Gemini prompt = code facts + activity findings
        |
        v
Output: docs with Project Activity and Health section + PNG plots
```

A second entry point, `docxpilot activity <path>`, runs only step 7 and prints the results. It needs no Gemini API key, which makes it ideal for lab demos and testing.

## 5. Signal definition

Build two signals from `git log --numstat --no-merges --format=@@%H|%aI` over the full history:

- `commits[n]`: number of commits on day n.
- `churn[n]`: lines added plus lines deleted on day n.

Rules:

- Convert each author timestamp to UTC and take the calendar date.
- Create one sample per day from the first commit day to the last commit day. Days with no commits are 0.
- numstat prints `-` for binary files. Treat those as 0 lines.
- Apply `np.log1p` to both signals to compress huge bursts before modeling.
- Stack into an array of shape (2, N).

## 6. DSP specification (use numpy and scipy)

Function `compute_dsp(signal) -> DspResult`:

1. **Detrend:** `scipy.signal.detrend` on the commit signal.
2. **Smoothing:** 4th-order Butterworth low-pass, cutoff 0.25 cycles/day (passes periods longer than 4 days), applied with `filtfilt` for zero phase. Also compute a 7-day moving average for plotting.
3. **Window and FFT:** multiply by a Hann window, zero-pad to the next power of two, take `np.fft.rfft`, frequencies from `np.fft.rfftfreq(nfft, d=1.0)`.
4. **Dominant period:** ignore DC and any frequency below 2/N. Take the highest peak in the magnitude spectrum, then period = 1/f in days. Also report peak strength = peak power divided by total power.
5. **Cross-check:** compute the autocorrelation and confirm the strongest lag between 2 and 60 days. Report both; flag a mismatch beyond 20 percent.
6. **STFT:** `scipy.signal.stft` with nperseg = 64, noverlap = 48, Hann window, for the spectrogram plot.
7. **Features:** spectral entropy, spectral flatness, burstiness = (std - mean) / (std + mean) of daily commits, active-day ratio.

Explain each step in code comments, because the lab report must justify the DSP choices.

## 7. Deep learning specification (use PyTorch)

**Model:** 1D convolutional autoencoder over sliding windows of 28 days.

- Input shape (batch, 2, 28), the two channels being log commits and log churn.
- Encoder: Conv1d(2, 16, k=5, pad=2), ReLU, MaxPool(2); Conv1d(16, 32, k=5, pad=2), ReLU, MaxPool(2); flatten (32 x 7 = 224); Linear(224, 16) as the latent code.
- Decoder: Linear(16, 224), reshape to (32, 7), Upsample(2), Conv1d(32, 16, k=5, pad=2), ReLU, Upsample(2), Conv1d(16, 2, k=5, pad=2).
- Loss: MSE. Optimizer: Adam, lr 1e-3, batch 64, up to 60 epochs, early stopping on validation loss with patience 8.

**Normalization:** divide each repo's signal by the 95th percentile of its nonzero days (after log1p), clip to 3. Save the exact procedure so inference matches training.

**Inference:** slide the window with stride 1 over the repo's signal, compute per-window reconstruction MSE, flag windows above the saved threshold, then merge overlapping flagged windows into date ranges. Label each range as a burst (mean activity above normal) or rhythm break (below or irregular).

**Threshold:** the 99th percentile of reconstruction error on the held-out validation windows, saved in `config.json` next to the weights.

**Important design note:** an autoencoder reconstructs a window of all zeros very easily, so it will not flag long silences. Therefore inactivity gaps are detected by a rule: a run of zero days longer than max(14, 3 x the median gap length). The autoencoder covers bursts and broken rhythms. Document this split in the report as a deliberate design decision.

**Optional stretch goal, only after everything else works:** an LSTM forecaster predicting the next 14 days of commits.

## 8. Data and training plan

No labeled data exists, so the plan is unsupervised training on normal activity plus synthetic anomaly injection for evaluation.

1. `ml/collect_data.py`: clones 15 to 20 public repositories into a temp folder, extracts the daily signals using the same function the analyzer uses, and saves them as `.npy` files. Pick repos with at least one year of history and moderate size, for example psf/requests, pallets/flask, pallets/click, Textualize/rich, tiangolo/typer, psf/black, encode/httpx, tiangolo/fastapi. Avoid giant repos such as linux or chromium.
2. `ml/synthetic.py`: generates extra signals (weekly seasonality, Poisson noise, occasional vacation gaps, slow trend) to enlarge the training set.
3. Split by repository, not by window: roughly 70 percent of repos for training, 15 percent for validation, 15 percent for test. This prevents leakage between neighboring windows.
4. `ml/train.py`: builds windows, trains, saves `src/ml/weights/activity_ae.pt` and `config.json` (normalization settings, threshold, window size, training date, repo list).
5. Fix random seeds. Log training and validation loss to a CSV and plot the loss curve for the report.

## 9. Integration, file by file

Existing code facts (verify in Phase 0): the project uses a `src` layout, flat imports (`from analyzers.models import ...`), `KnowledgeAggregator.aggregate()` runs a `steps` list of (label, method) pairs under a rich progress bar, `analyze_git()` currently reads only the last 20 commits through a `run_git_command` helper with a 30-second timeout, and `ProjectKnowledge` is the single object passed to Gemini.

| File | Change |
| --- | --- |
| `src/analyzers/activity_analyzer.py` | NEW. `analyze_activity(project_path) -> ActivityReport`. Orchestrates signal extraction, DSP, DL, plots |
| `src/analyzers/activity_signal.py` | NEW. `build_signals(project_path)` returning dates and the (2, N) array |
| `src/analyzers/activity_dsp.py` | NEW. `compute_dsp(...)` from Section 6 |
| `src/ml/__init__.py`, `model.py`, `infer.py`, `train.py`, `collect_data.py`, `synthetic.py` | NEW. Autoencoder, inference, training scripts |
| `src/ml/weights/` | NEW. `activity_ae.pt`, `config.json` |
| `src/analyzers/models.py` | ADD `ActivityAnomaly`, `ActivityReport`, and `activity: ActivityReport` on `ProjectKnowledge` (with a default) |
| `src/aggregator/knowledge_base.py` | ADD step `('Activity signal', self._run_activity_analyzer)` after the docs reader, plus the method |
| `src/ai/prompts.py` | ADD an activity findings block to the prompt and an instruction to write a Project Activity and Health section using only those facts |
| `src/output/writer.py` | SAVE the PNG plots next to the generated docs and reference them from the docs |
| `src/cli/commands.py` | ADD `--no-activity` flag on generate and a new `activity` command |
| `pyproject.toml`, `requirements.txt` | ADD numpy, scipy, matplotlib, torch. Include the weights as package data |
| `tests/` | NEW. See Section 13 |

Do not modify the six existing analyzers. Use a separate full-history git call with a 120-second timeout and `encoding='utf-8', errors='replace'` instead of editing `analyze_git`.

## 10. Data models

```python
@dataclass
class ActivityAnomaly:
    start_date: str
    end_date: str
    kind: str          # burst, rhythm_break, inactivity_gap
    score: float       # reconstruction error ratio, or gap length in days
    description: str = ''

@dataclass
class ActivityReport:
    available: bool = False
    reason: str = ''               # why unavailable, if so
    span_days: int = 0
    active_days: int = 0
    total_commits: int = 0
    dominant_period_days: float = 0.0
    dominant_strength: float = 0.0
    spectral_entropy: float = 0.0
    burstiness: float = 0.0
    anomalies: list[ActivityAnomaly] = field(default_factory=list)
    model_used: bool = False       # False if torch or weights missing
    plot_paths: list[str] = field(default_factory=list)
    summary_lines: list[str] = field(default_factory=list)
```

## 11. CLI changes

- `docxpilot generate <path> [--no-activity]`: unchanged behavior plus the new step.
- `docxpilot activity <path> [--out DIR]`: runs only the analyzer, prints the rich summary, saves the three plots. Works without a Gemini key.

## 12. Phased implementation plan

**Phase 0: Preparation**

- Read `cli/commands.py`, `cli/ui.py`, `aggregator/knowledge_base.py`, `analyzers/models.py`, `analyzers/git_analyzer.py`, `ai/prompts.py`, `ai/doc_generator.py`, `output/writer.py`.
- `requirements.txt` is saved as UTF-16, which pip can fail to read. Re-save it as UTF-8 and make it match the dependencies in `pyproject.toml`.
- Create a virtual environment and install dependencies. Confirm `docxpilot` still runs.
- Acceptance: the existing tool runs unchanged on its own folder.

**Phase 1: Signal extraction**

- Implement `activity_signal.py` per Section 5.
- Acceptance: running on the DocXPilot repo returns correct day counts. Sum of `commits` equals `git rev-list --no-merges --count HEAD`. Non-git folders return a clean error value, not an exception.

**Phase 2: DSP core**

- Implement `activity_dsp.py` and the three plots.
- Acceptance: on a synthetic signal with a 7-day sine plus noise, the dominant period is within 7 plus or minus 0.5 days. Plots render headless with the matplotlib Agg backend.

**Phase 3: Integration without deep learning**

- Add the dataclasses, aggregator step, `activity` CLI command, and the gap rule. Set `model_used = False`.
- Acceptance: `docxpilot activity .` prints a summary and saves plots. `docxpilot generate .` still works end to end and `--no-activity` skips the step.

**Phase 4: Data and model training**

- Implement `collect_data.py`, `synthetic.py`, `model.py`, `train.py`.
- Acceptance: training runs reproducibly, validation loss decreases, weights and `config.json` are saved, loss curve is plotted.

**Phase 5: Model inference in the analyzer**

- Implement `infer.py`, load weights lazily (import torch only when needed), flag windows, merge them into date ranges.
- Acceptance: with torch and weights present, `model_used = True` and anomalies are reported. With torch or weights missing, the DSP results still work and the report explains why the model was skipped.

**Phase 6: Prompt, writer, and docs output**

- Update `prompts.py` and `writer.py` as in Section 9.
- Acceptance: generated docs contain the Project Activity and Health section, the numbers match the terminal summary, and PNGs sit next to the docs. The prompt tells Gemini not to invent numbers.

**Phase 7: Tests and evaluation**

- Implement the tests and evaluation script from Section 13.
- Acceptance: all tests pass and the evaluation table is generated.

**Phase 8: Polish and lab deliverables**

- Add a README section, a demo script, and collect figures for the report (Section 14).
- Acceptance: a clean clone installs and runs `docxpilot activity .` successfully.

## 13. Edge cases, testing, and evaluation

**Edge cases to handle explicitly**

- Not a git repository, git not installed, or an empty repository.
- Fewer than 60 days of history or fewer than 30 commits: set `available = False` with a clear reason, never crash.
- Shallow clones (history truncated): warn the user.
- Very large repositories: cap analysis to the most recent 3 years and the 120-second timeout.
- Windows paths and consoles: use `pathlib`, UTF-8 subprocess output, and the Agg matplotlib backend.
- torch not installed or weights missing: degrade to DSP-only without error.

**Unit tests (pytest, in `tests/`)**

- Signal builder on a temporary git repo created with fixed commit dates.
- FFT peak detection on synthetic signals with known periods (5, 7, 14 days).
- Gap rule triggers on a long zero run and not on short ones.
- Short history returns `available = False`.
- Inference output shapes and threshold logic with a tiny dummy model.

**Evaluation for the lab report**

Because real anomaly labels do not exist, inject known anomalies into held-out test signals: bursts (3 to 8 times normal for 1 to 3 days) and rhythm breaks (weekly pattern scrambled for 2 to 3 weeks). Then measure window-level precision, recall, and F1.

Compare three detectors in one table:

1. Rolling z-score baseline (28-day window, absolute z above 3).
2. DSP-only spectral feature change detector.
3. The trained autoencoder.

Report results on repos the model never saw during training. Include ablation notes, for example the effect of window size 14 versus 28 versus 56.

## 14. Deliverables for the lab

- Source code and trained weights, with a one-command demo (`docxpilot activity .`).
- Figures: raw versus filtered signal, magnitude spectrum, spectrogram, anomaly overlay, training loss curve, evaluation table.
- Short report with these sections: problem statement, signal model, DSP pipeline and justification of each filter and window choice, network architecture, training setup and data split, results and comparison with baselines, limitations (needs enough history, autoencoder cannot see silences, daily sampling hides intra-day patterns).
- One-sentence justification for the professor: the project models repository activity as a discrete-time signal, applies filtering and spectral analysis, and trains a neural autoencoder for anomaly detection.

## 15. Safety checks before sharing or submitting

- The project folder contains a `.env` file. Make sure it holds no real API key you are about to share or commit. Rotate the key if it was ever committed, and add `.env` to `.gitignore`.
- Remove `__pycache__` folders and the `.egg-info` folder from what you submit.
- Do not commit the cloned training repositories, only the extracted `.npy` signals or the scripts that recreate them.

</USER_REQUEST>
<ADDITIONAL_METADATA>
The current local time is: 2026-10-13T22:07:32+05:30.

The user's current state is as follows:
Active Document: c:\Users\pranav\Downloads\DocXPilot Activity Signal Analyzer Overall and Implementation Plan.md (LANGUAGE_MARKDOWN)
Cursor is on line: 282
Other open documents:
- d:\Projects\DocXPilot\.env (LANGUAGE_UNSPECIFIED)
- c:\Users\pranav\Downloads\DocXPilot Activity Signal Analyzer Overall and Implementation Plan.md (LANGUAGE_MARKDOWN)
Browser State:
  Page BD49EA86844D4295A57324C2A7813F55 (Vantage widget) - https://vantage.csw.lenovo.com/v1/web/containerwidget/default/ [ACTIVE]
    Viewport: 64x64, Page Height: 64
</ADDITIONAL_METADATA>