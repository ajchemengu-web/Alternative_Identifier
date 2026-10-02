# Data Protection Impact Assessment (DPIA) — Smart Gen

> **Status: DRAFT TEMPLATE — not legal advice, not yet a valid DPIA.**
> Everything marked `[ ]` must be completed by the institution (the data
> controller). Everything else was written by the engineers from what the
> code in this repository actually does, as of the date in §0, and has a file
> reference so it can be checked. Have your Data Protection Officer and
> Kenyan counsel review the legal framing before relying on it.

**Why this exists.** Smart Gen turns students' faces into biometric
templates. Under the Data Protection Act, 2019 (the "Act"), a DPIA must be
carried out *before* processing that is likely to be high risk, and the
Data Protection (General) Regulations, 2021 name biometric data
specifically. In November 2025 the High Court halted a broadcaster's
facial-recognition system as unlawful under the Constitution and the Act,
treating facial templates as sensitive personal data for which a DPIA is
required before deployment. Statute references below are to the Act and Regulations as summarised
in public sources — **verify the current text and the Office of the Data
Protection Commissioner's (ODPC) biometric guidance note before relying on
any section number or deadline.**

How it is organised: §2–§5 follow the four things the Act says a DPIA must
contain — (a) systematic description, (b) necessity and proportionality,
(c) risks to data subjects, (d) measures and safeguards.

---

## 0. Document control

| | |
|---|---|
| Institution (data controller) | `[ ]` |
| Registered with ODPC? Registration no. | `[ ]` |
| Data Protection Officer | `[ ]` name, contact |
| DPIA owner / author | `[ ]` |
| Version / date | `0.1` / `[ ]` |
| Software baseline described | `Alternative_Identifier` commit `[ ]`, consent notice version `2026-09-v1` |
| Status | Draft — not approved |
| Next review due | `[ ]` (at least annually, and on any trigger in §8) |

---

## 1. Summary and why a DPIA is required

Smart Gen has two products on one backend:

- **SmartAccess** — facial-recognition access control at campus/hostel
  checkpoints, with a guard dashboard for unrecognised visitors.
- **SmartAttendance** — class attendance recorded from classroom cameras,
  with a student/lecturer mobile app.

It is high risk because it involves: **biometric data** (a facial template
is sensitive personal data), **continuous monitoring** of people in
places they must be, **young adults and possibly minors**, a **power
imbalance** (access to housing and classes depends on participating), and
**automated decisions** (a face match can admit or refuse a person).

Overall conclusion: `[ ]` proceed / proceed with conditions / do not proceed
— to be completed after §4–§6. *Engineers' view:* the system should not
go live for real students until the High-rated open items in §4 are closed.

---

## 2. (a) Systematic description of the processing

### 2.1 Purposes

1. Recognise enrolled students at campus and hostel checkpoints so access
   can be granted or refused, and keep a record of entries.
2. Record which enrolled students attend a timetabled class, and notify
   them and the lecturer of the outcome.
3. Identify and track persons of interest on a security watchlist
   (Security Admin only).

Not purposes: marketing, profiling, selling data, emotion or attribute
inference. `[ ]` institution to confirm this list is complete and that no
other use is intended.

### 2.2 How it works (data flow)

1. **Registration.** An admin creates the student record (no face).
2. **Consent.** The student reads the consent notice in the app and
   agrees — or an admin confirms the student agreed (recorded against the
   admin). Without a consent record the backend refuses to create a face
   template (`src/services/consent_service.py`,
   `src/services/enrollment_service.py`).
3. **Enrolment.** The student takes live photos (liveness-checked) or an
   admin uploads photos. Each photo is turned into an embedding in memory;
   the photos are **not stored**. Embeddings are averaged into one
   template saved as a `.npy` file, referenced from `students.embedding_file`.
4. **Recognition.** A camera frame is turned into an embedding and
   compared (cosine similarity, threshold `MATCH_THRESHOLD = 0.50`) with
   stored templates, after a passive liveness check
   (`LIVENESS_THRESHOLD = 0.55`). Checkpoint results are written to
   `access_logs`; classroom results to `attendance_records`.
5. **Unrecognised visitors.** The frame is saved as a JPEG with its
   embedding and queued for a guard to admit or reject
   (`src/services/unknown_service.py`).
6. **Outcomes.** Students see attendance history and notifications;
   lecturers see rolls for classes they teach; guards/admins see access
   logs; Security Admins see watchlist sightings.
7. **End of life.** Student withdraws consent (face template deleted), or
   an Original Admin erases the student (`src/services/erasure_service.py`).

### 2.3 Data inventory

| Data | Where | Personal / sensitive | Source |
|---|---|---|---|
| Student record: student id, name, admission no., hostel, room, department, course, year, semester | `students` | Personal | Admin |
| **Face template** (numeric embedding) — encrypted at rest | `data/embeddings/*.npy` | **Sensitive (biometric)** | Student / admin enrolment |
| Login: username, email, bcrypt password hash, role, tier | `users` | Personal | Admin |
| Access log: person type, id, entrance, match score, decision, guard id, liveness score, timestamp | `access_logs` | Personal (location + time of a named person) | Camera |
| Class attendance records and "you attended / missed" notifications | `attendance_records`, `attendance_notifications` | Personal | Camera |
| Consent history: notice version, channel (self / admin-assisted), who recorded, granted/withdrawn times | `biometric_consents` | Personal | Student / admin |
| **Unrecognised-visitor image + embedding** | `data/unknowns/` | **Sensitive (biometric)** — *of people who never agreed* | Camera |
| Guest (admitted visitor) photo + embedding | `data/guests/` | **Sensitive (biometric)** | Camera |
| Watchlist target: name, description, reason, face template, status, sightings | `watchlist_targets`, `access_logs` | **Sensitive**; may relate to suspected offences | Security Admin |
| Erasure log: reference, fixed reason, admin, counts — **no identity** | `data_erasure_log` | Not personal by design | System |

Legacy/dev scripts (`src/enrollment.py`, `src/guest_manager.py`) also
write face **photos** to disk (`data/faces/…`, `data/guests/photos/`).
They are not part of the API but are in the repository.

### 2.4 Data subjects

Enrolled students (`[ ]` approximate number; `[ ]` any under 18?);
lecturers and staff whose logins exist (their faces are **not** enrolled —
`students` table only); admitted guests; **unrecognised visitors and
passers-by captured by checkpoint cameras**; persons on the watchlist.

### 2.5 Who can see what

| Role | Access |
|---|---|
| Student | Own profile, attendance, notifications, consent |
| Lecturer | Rolls for classes they teach (names + present/absent) |
| Guard | Pending unknown-visitor queue, access log |
| Original Admin | Everything above; camera management; erasure; retention sweep |
| Security Admin | Watchlist, investigations, scene reconstruction |
| Timetabling / Dean | Timetable; Dean also a department roster/summary |
| Temporary Admin | Intended: enrolment only; expires when an Original Admin marks the task done |

Enforced server-side by role/tier checks (`src/api/deps.py`). Personal-data
endpoints are limited to the tiers that need them: the student list,
guest list, access log, analytics and the guard queue to Original and
Security admins (and guards for the log/queue); student enrolment to Original,
Security and Temporary admins; creating login accounts (`POST /enroll`, which
can mint any role including other admins) to the Original admin only; the lecturer list to Original and
Timetabling; cameras to Original, Security and Dean. **No endpoint accepts
"any admin" any more** (a test fails if one does). **Still open:** the
Dean role is not restricted to its own department on the server
(department is just a request parameter, because a Dean's account does not
record which department it belongs to), and nothing logs who viewed what.
See R3.

### 2.6 Processors, hosting and transfers — `[ ]` to complete

| Component | Provider | Location of data | Contract / DPA |
|---|---|---|---|
| Recognition API + face templates | `[ ]` (currently the developer's laptop via tunnel; hosting not yet chosen) | `[ ]` | `[ ]` |
| Database | SQLite locally; Supabase Postgres planned | `[ ]` region | `[ ]` |
| Web dashboards | Vercel (server-side calls only; no biometric data stored) | n/a | `[ ]` |
| Mobile/web app | Vercel / GitHub Pages (static); calls the API directly | n/a | `[ ]` |

Cross-border transfer rules and any data-localisation requirement for
biometric data must be checked against the Act and Regulations: `[ ]`.

### 2.7 Retention (what the code actually does today)

| Data | Retention in code | Gap |
|---|---|---|
| Face template (student) | Until consent withdrawn or student erased | No automatic deletion at graduation — relies on an admin action (matches PRD §9.4) |
| Access logs | **Kept indefinitely** — nothing deletes them except student erasure | `[ ]` institution must set a period (suggest a short, justified one) |
| Attendance records / notifications | Kept indefinitely except on student erasure | `[ ]` set a period |
| Rejected visitor image + embedding | Deleted immediately on rejection | — |
| Admitted guest image + embedding | Deleted ~24 h after admission (hourly sweep) | — |
| **Unrecognised visitor, not yet reviewed** | **No expiry** while `PENDING_REVIEW` | If no guard acts, the face sits indefinitely |
| Watchlist target face template | Kept after the target is **resolved** (reactivation possible) | `[ ]` decide whether resolved ⇒ delete |
| Consent history | Kept while the student exists; deleted on erasure | — |
| Erasure log | Kept (no identity in it) | — |

---

## 3. (b) Necessity and proportionality

### 3.1 Lawful basis — `[ ]` institution to decide with counsel

The software currently relies on **consent** for enrolling a student's
face. Points to resolve:

- **Is consent genuinely free?** Where access to housing or classes
  effectively depends on enrolling, consent may not be valid. The notice
  tells students they may decline and to ask about an alternative — **an
  alternative route (e.g. ID card + manual register) must actually exist
  and be as easy.** `[ ]` describe it.
- **Minors.** The consent flow does not ask a student's age or obtain a
  parent/guardian's consent. If any student may be under 18, the ODPC
  guidance on children's data applies. `[ ]`
- **Unrecognised visitors never consent** to having their face captured
  and stored. This needs its own lawful basis, signage, and a short
  retention period. `[ ]`
- **Watchlist processing** may involve data about alleged offences and
  needs its own basis and safeguards. `[ ]`

### 3.2 Necessity — less intrusive alternatives considered `[ ]`

Complete honestly. Prompts: ID card/QR, PIN, fingerprint (also biometric),
guard visual check, roll-call/lecturer register. For each: why it is or is
not sufficient for the purpose in §2.1.

### 3.3 Proportionality, accuracy and fairness

- **Minimisation:** only a template is kept for enrolled students;
  photos are discarded. Lecturers and staff are not enrolled. Data
  collected is limited to what §2.3 lists.
- **Accuracy — not validated.** `MATCH_THRESHOLD` was set for a larger
  model and has not been re-tuned for the `buffalo_s` model now in use
  (noted in `recognition_service.py`). There has been **no accuracy or
  bias testing on the institution's own student population**. Face
  recognition error rates can differ by skin tone, gender and age; a false
  rejection means a student is wrongly refused or marked absent, a false
  match means someone else is admitted or marked present. `[ ]` test plan,
  acceptable error rates, and a human override process. A false-positive
  flag exists for guards and lecturers (PRD §9.7).
- **Liveness** is a passive heuristic, not independently validated.
- **Automated decisions.** A face match can admit or refuse. Check whether
  the Act's provisions on automated individual decision-making apply and
  keep a human able to override. `[ ]`

### 3.4 Transparency and data-subject rights

| Right | Status in the product |
|---|---|
| Be informed | Consent notice served by the API and shown in the app and on the admin form (`GET /consent/notice`). Needs institution name/contact set via `CONSENT_CONTROLLER_NAME`, `CONSENT_CONTACT`, and **signage at cameras** (not built). |
| Withdraw consent | Built: Profile → Withdraw. Deletes the face template. |
| Erasure | Built for admins: `POST /admin/students/erase` (see Appendix D). No self-service request channel. |
| Access to own data | **Not built.** No export. Students can see their own attendance/notifications only. |
| Rectification | **Not built** as a student-facing feature. |
| Object / restrict | No mechanism beyond withdrawing consent. `[ ]` |
| Complain | `[ ]` publish route to the controller and the ODPC |

---

## 4. (c) Risks to data subjects

Likelihood (L) and severity (S): `[ ]` institution to score 1–5 and
compute rating. The "Engineers' draft" column is only a starting
suggestion from reading the code. **Status** is what the repository does
today.

| # | Risk | Status today | Engineers' draft |
|---|---|---|---|
| R1 | **Biometric data exposed publicly.** `data/` is **committed to git and the repository is public**, since the first commit on 2026-09-03: 110 face photos (20 in `data/faces/`, 89 unrecognised-visitor images, 1 guest photo), 97 face-template files, and the SQLite database. | **Open — incident.** See §7. | **High** |
| R2 | **Biometric data not fully encrypted at rest.** PRD §9.5 makes encryption at rest a hard requirement. **Face templates** (`.npy`) are now encrypted with AES-256-GCM (`template_store.py`), once a key is set and `migrate` has been run. **Still unencrypted:** the database (student, access-log and attendance records), unrecognised-visitor and guest **photos**, and the legacy `data/faces` photos. Templates already committed to git, backups or disk remnants stay readable in those copies. Anyone with the running server also has the key. | **Partly mitigated** (templates only; needs key set + migration run) | **Medium–High** until the DB and photos are covered |
| R3 | **Function creep / unauthorised internal access.** Admin tiers are now limited to the data they need (Temporary, Timetabling and Dean can no longer read the student list or access log). **Still open:** a Dean can read any department's roster/summary by changing a request parameter; there is no audit log of who viewed what; Original and Security admins can still see everyone. | **Partly mitigated** | **Medium–High** |
| R4 | **Unlawful or invalid consent** (power imbalance, minors, no alternative route). | Partly mitigated (notice, record, withdrawal) | High until §3.1 resolved |
| R5 | **Misidentification** — wrong refusal/absence or wrong admission; unequal error rates across groups. | Open — not tested | High |
| R6 | **Spoofing** — photo/screen held to a camera. | Mitigated (passive liveness); not independently tested | Medium |
| R7 | **Over-retention.** Access logs and attendance kept forever; unreviewed visitor faces never expire; resolved watchlist faces kept. | Open | Medium–High |
| R8 | **Capture of non-consenting people** (visitors, passers-by) at checkpoint cameras. | Partly mitigated (reject ⇒ immediate delete; admit ⇒ 24 h) | Medium |
| R9 | **Insecure transport/API.** CORS allows all origins; no rate limiting; tokens last 12 h; TLS depends on the host chosen. | Open | Medium |
| R10 | **Right to access/rectification unmet.** | Open | Medium |
| R11 | **Erasure incomplete** — copies in git history, backups, exports, watchlist records. | Partly mitigated (erasure endpoint; reports what it keeps) | Medium |
| R12 | **Breach not detected or not reported in time** (72-hour rule, Act s.43). | Open — no runbook (see Appendix C) | Medium |
| R13 | **Cross-border / third-party processing** unknown while hosting is undecided. | Open | `[ ]` |
| R14 | **Data subjects unaware** (no signage at cameras). | Open | Medium |

---

## 5. (d) Measures and safeguards

### 5.1 Implemented (verifiable in the repository)

- Consent notice, version-tracked consent records, enforcement in the
  service layer on both enrolment paths, withdrawal that deletes the
  template and clears the live recognition cache.
- Liveness check on self-enrolment and recognition.
- bcrypt password hashing; signed JWTs; server-side role and admin-tier
  checks on every non-public endpoint.
- Row Level Security enabled on all tables in the Supabase schema.
- Face templates encrypted at rest (AES-256-GCM, per-write nonce, file name
  bound into the authentication so a template can't be swapped onto another
  person; key ring for rotation; atomic writes; server refuses to start
  without a key unless explicitly opted out; `migrate` command with dry run
  and verify-before-replace). **Scope: templates only** — see R2.
- Immediate deletion of rejected-visitor data; 24-hour expiry of admitted
  guests; hourly retention sweep.
- Admin erasure with dry run, confirmation, fixed-choice reasons,
  all-or-nothing database transaction, identity-free erasure log, and
  refusal while an active watchlist target is linked.
- Consent shown to the admin as well, with the admin's confirmation
  recorded when they enrol on a student's behalf.

### 5.2 Required before real deployment — owner/date `[ ]`

| Item | Addresses |
|---|---|
| Make the repository private **and** remove `data/` from git history; treat anything ever pushed as exposed; add `data/` and `*.db` to `.gitignore` | R1 |
| Set `TEMPLATE_ENCRYPTION_KEYS` from the host's secret store, back the key up separately from the data, run `python -m src.encrypt_templates migrate`, then set `TEMPLATE_REQUIRE_ENCRYPTED=1` | R2 |
| Encrypt the database and the visitor/guest/legacy photos at rest (disk or database-level encryption, or stop keeping the photos); decide who holds the key and how it is rotated | R2 |
| Decide lawful basis; provide a real alternative route; handle under-18s | R4 |
| Accuracy/bias test on local data; re-tune the threshold; define a human override | R5 |
| Retention schedule for logs/attendance; expiry for unreviewed visitors and resolved watchlist faces | R7 |
| Scope Dean to its own department server-side (needs a department on the Dean's account); audit log of who viewed personal data | R3 |
| Restrict CORS to known origins; rate-limit login and recognition endpoints; shorter token life; confirm TLS | R9 |
| Student data-access/export and correction process | R10 |
| Camera signage and a public privacy notice | R14, §3.4 |
| Breach runbook, tested (Appendix C) | R12 |
| Choose hosting, confirm location, sign processor agreements | R13 |
| Register with the ODPC; keep the registration current | §6 |

### 5.3 Residual risk after the above — `[ ]`

---

## 6. Consultation and regulator engagement

- DPO consulted: `[ ]` date, advice, response.
- Student representatives / a sample of data subjects consulted: `[ ]`.
- **ODPC.** The Act requires consulting the Commissioner before processing
  where the DPIA shows high residual risk, and the Regulations set a
  submission timeline before processing (reported as 60 days, with
  deemed approval if there is no response — **verify**). `[ ]` decision,
  date submitted, reference.

---

## 7. Known incident to resolve first (R1)

On review for this DPIA it was found that the backend repository is
**public** and contains, since 2026-09-03: 110 face photos (20 in
`data/faces/`, 89 unrecognised-visitor images, 1 guest photo), 97
face-template files, and the SQLite database `data/smarthostel.db`
(4 student records, access logs, guest and unrecognised-visitor rows). Whether these are test data
or real people's is `[ ]` to be confirmed by the institution.

Suggested order (each step needs a human decision):

1. Make the repository **private** immediately.
2. **Copy `data/` somewhere safe first** — untracking it and pulling will
   delete those files from working copies.
3. Add `data/` and `*.db` to `.gitignore`; `git rm -r --cached data`.
4. Purge history (`git filter-repo`) and force-push, then ask GitHub
   support to clear cached views. Assume forks and clones may exist.
5. Decide, with counsel, whether this is a notifiable breach (Act s.43:
   unauthorised access/acquisition **and** a real risk of harm; 72 hours
   from becoming aware, with reasons for any delay) and whether people
   must be told. Record the decision and the reasoning either way.

---

## 8. Sign-off and review

| | Name | Date | Decision |
|---|---|---|---|
| DPIA owner | `[ ]` | `[ ]` | |
| DPO | `[ ]` | `[ ]` | |
| Senior responsible officer | `[ ]` | `[ ]` | |

**Review again when:** a new camera type or location is added; the
recognition model or thresholds change; the consent notice version
changes; a new recipient or processor is added; hosting changes; any
incident or breach occurs; a complaint is upheld; or at least annually.

---

## Appendix A — Where each claim is implemented

| Claim | File |
|---|---|
| Consent notice, records, versioning | `src/services/consent_service.py` |
| Consent enforced on enrolment; withdrawal deletes template | `src/services/enrollment_service.py` |
| Endpoints (`/consent/notice`, `/me/consent*`, `/admin/students/*`) | `src/api/main.py` |
| Erasure | `src/services/erasure_service.py` |
| Face-template encryption, key handling, migration | `src/services/template_store.py`, `src/encrypt_templates.py` |
| Thresholds and cache | `src/services/recognition_service.py`, `src/services/liveness_service.py` |
| Unrecognised visitors / retention | `src/services/unknown_service.py`, `src/services/retention_service.py` |
| Role and tier checks (`require_access`, `require_admin_tier`); tier groups | `src/api/deps.py`, `src/api/main.py` |
| Schema, RLS | `supabase/schema.sql`, `src/database.py` |
| Tests | `src/test_consent_service.py`, `src/test_erasure_service.py`, `src/test_api_routes.py`, `src/test_enrollment_service.py`, `src/test_template_store.py` |

## Appendix B — Pre-deployment checklist

- [ ] ODPC registration current
- [ ] DPIA completed, signed, and (if required) submitted
- [ ] Repository private, `data/` purged from history (§7)
- [ ] Template encryption key set, backed up separately, `migrate` run, strict mode on
- [ ] Database and photos encrypted at rest (not covered by template encryption)
- [ ] Consent notice reviewed by counsel; `CONSENT_CONTROLLER_NAME` and `CONSENT_CONTACT` set
- [ ] Alternative non-biometric route exists and is announced
- [ ] Under-18 handling decided
- [ ] Accuracy/bias tested; threshold set; override process defined
- [ ] Retention periods set and enforced for logs, attendance, visitors, resolved watchlist
- [ ] Camera signage installed
- [ ] Hosting and processor agreements signed; data location confirmed
- [ ] CORS restricted, rate limiting on, TLS confirmed
- [ ] Breach runbook written and rehearsed
- [ ] Staff trained: guards, admins, lecturers

## Appendix C — Breach quick card

If personal data may have been accessed or taken by someone not authorised:

1. Note the time you became aware. The Act's clock is **72 hours** to
   notify the Commissioner where there is a real risk of harm (s.43;
   verify). Late notification must explain the delay.
2. Contain: revoke tokens (rotate `JWT_SECRET`), change database
   credentials, make exposed repositories/buckets private.
3. Tell the DPO. Record what was exposed, whose, since when, how found.
4. Decide, with counsel, on notifying the ODPC and the people affected.
5. Write down the decision and reasons even if you decide not to notify.

## Appendix D — Erasing a student (Original Admin)

Dry run (counts only, changes nothing):

    GET /admin/students/data-summary?student_id=<id>

Erase:

    POST /admin/students/erase
    { "student_id": "<id>", "confirm": "<id again>", "reason": "GRADUATED" }

`reason` is one of `GRADUATED`, `LEFT_INSTITUTION`, `SUBJECT_REQUEST`,
`OTHER` — a fixed list on purpose, so no one's name ends up in the log.
Give the returned `erasure_reference` to the person as proof; the log
itself cannot identify them.

**Erased:** student record, login, access-log entries, attendance records
and notifications, consent history, face template file.

**Refused (409):** while the student is linked to an *active* watchlist
target — ask the Security Admin to resolve it first.

**Kept and reported (`retained_for_review`):** a *resolved* watchlist
target's own record (name, reason, sightings). Its copy of the face and its
link to the student are removed.

**Not covered:** git history, backups, exports, anything outside the
application. Erasure through this endpoint is therefore not complete
until those are dealt with (§7).
