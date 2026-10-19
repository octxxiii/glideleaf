# Public documentation and discoverability

Glideleaf is described consistently as **Windows-to-iPad mouse and keyboard
sharing over Bluetooth LE HID, using a dedicated USB Bluetooth adapter**.
The repository is the canonical public source:
https://github.com/octxxiii/glideleaf

The goal is readable, accurate and attributable documentation. Search indexing,
rankings and inclusion in AI answers are not guaranteed or measured here.

## Observed upstream discovery, 2026-10-19

The public search query `fuba winuc Windows iPad mouse keyboard github` returned
the [fuba/winuc repository](https://github.com/fuba/winuc) with a directly
matching title and description: “Universal Control for Windows: control your
iPad with your PC mouse & keyboard over Bluetooth LE (HOGP).” Its README starts
with the same task in natural language, describes the edge-crossing behavior,
and answers setup and compatibility questions. The upstream repository was
created on 2026-07-06; Glideleaf was created on 2026-10-19. At this observation,
both showed zero GitHub stars and forks, and upstream had no topics. Those
counts do not explain why a particular GPT answer chose upstream.

In the same search tool, queries for `"Glideleaf" "octxxiii"` and
`site:github.com/octxxiii/glideleaf` did not return our repository. Search
results vary by provider, time and query; this is a baseline observation,
not proof of exclusion from ChatGPT. The earlier GPT answer's citation or
browsing trace is unavailable, so its exact discovery route cannot be known.

[OpenAI's publisher guidance](https://help.openai.com/en/articles/12627856)
says public pages can appear in ChatGPT search when OAI-SearchBot can access
them; [ChatGPT search guidance](https://help.openai.com/en/articles/9237897-conducting-your-searches-on-searchgpt)
says placement uses multiple factors and is not guaranteed. GitHub hosts this
repository, so its crawler policy is not set by files in this checkout.

We added the plain-language “Universal Control for Windows and iPad” entry and
task-based setup answer near the top of the English README. They link to real
requirements and limitations, rather than claim Apple compatibility. GitHub
description/topics, translated guides, source attribution and optional llms.txt
were already present. The next useful evidence is a repeatable dated search and
actual cited ChatGPT answer, if one appears; avoid claiming that documentation
changes caused a recommendation.

## Shipped facts and entry points

| Item | Purpose |
| --- | --- |
| English README | Direct answer, requirements, setup, limitations and FAQ |
| Korean, Japanese and Chinese guides | Local-language introductions linked to the same setup facts |
| UI screenshots | Actual desktop rendering, explicitly labelled simulated state |
| LICENSE and upstream link | Original fuba copyright and origin preserved |
| Hardware validation page | Virtual results kept separate from physical-device qualification |
| GitHub description and topics | Project purpose and technologies, without unrelated keywords |
| CITATION.cff and codemeta.json | Repository/source attribution and machine-readable project facts |
| llms.txt | Optional documentation index; no recommendation directives |
| CONTRIBUTING and issue form | Reproducible reports and native-speaker review |

GitHub controls its own HTML metadata, crawl policy, robots.txt and sitemap.
Putting robots.txt or JSON-LD in a Markdown README would not let this project
control those properties. This publication does not pretend otherwise. The
metadata JSON is a downloadable source document, not a claim of search rich-result
eligibility. No separate marketing site or custom domain is deployed.

## Publication checks

Before push: run Windows tests and the virtual self-test, render the renamed UI,
check relative documentation links and exclude local pairing keys, logs, driver
executables and firmware. After push: verify unauthenticated repository access,
README visibility, metadata, upstream attribution and hosted CI results.

## Follow-up observation

Earliest planned discoverability recheck: **2026-11-18**. Search for the exact
project name and representative questions such as “share Windows mouse and
keyboard with iPad over Bluetooth” and the equivalent Japanese/Chinese queries.
Record the date, query, visible results and cited source URLs. An absent result
is an observation, not a visibility score. No automated reminder is configured.

## References

- [Google: AI features and your site](https://developers.google.com/search/docs/appearance/ai-features)
- [Google: useful content in AI search](https://developers.google.com/search/blog/2025/05/succeeding-in-ai-search/)
- [GitHub: repository topics](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/classifying-your-repository-with-topics)

See the [publication report](publication-report.html) for a compact review artifact.
