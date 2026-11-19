# Kit lavoro

Plugin e skill di Claude Code da avere sul computer di lavoro, a livello utente (valgono in ogni repo). Li installa `/kit lavoro`, una voce alla volta, dopo `scan-before-install` e dopo il tuo sì. Niente si installa da solo: questa lista è una proposta, la tabella la modifichi solo tu.

**Prima di tutto la regola dell'azienda.** Chiedi a chi gestisce la sicurezza se puoi installare plugin e skill di terze parti e cosa può arrivare al modello (ADR-002). Finché non lo sai, `/kit lavoro` si ferma. Se Claude Code è gestito dall'azienda, le sue impostazioni possono bloccare alcuni marketplace: vale la loro regola.

| Voce | Tipo | Origine | A cosa serve | Accessi nuovi | Proposto |
|---|---|---|---|---|---|
| superpowers | plugin | `superpowers@claude-plugins-official` (marketplace `anthropics/claude-plugins-official`) | piani, TDD, debugging, richieste di review | nessuno | sì |
| ponytail | plugin | `ponytail@ponytail` (marketplace `DietrichGebert/ponytail`) | la soluzione più semplice che funziona | nessuno | sì |
| owasp-security | plugin | `owasp-security@agamm` (marketplace `agamm/claude-code-owasp`) | review di sicurezza su OWASP e ASVS | nessuno | sì |
| playwright | plugin | `playwright@claude-plugins-official` | test E2E in un browser locale | apre un browser sul computer | dopo |
| grilling | skill | `https://github.com/mattpocock/skills`, cartella `skills/productivity/grilling` | mettere alla prova un piano prima di farlo | nessuno | sì |
| domain-modeling | skill | `https://github.com/mattpocock/skills`, cartella `skills/engineering/domain-modeling` | glossario e ADR del progetto | nessuno | sì |
| codebase-design | skill | `https://github.com/mattpocock/skills`, cartella `skills/engineering/codebase-design` | confini dei moduli, utile in una migrazione | nessuno | sì |
| to-tickets | skill | `https://github.com/mattpocock/skills`, cartella `skills/engineering/to-tickets` | da una spec a ticket piccoli | nessuno | sì |
| engineering | plugin | marketplace di claude.ai dell'organizzazione, se c'è: `claude plugin marketplace list`, poi `claude plugin marketplace add --claudeai <nome>` | standup, architettura, debito tecnico; connettori Jira e Slack | legge e scrive Jira e Slack con il tuo account | no |

Una voce con accessi nuovi si propone solo se la regola dell'azienda li ammette. Le skill personali (bozze, social, design del sito) restano fuori da questo kit.
