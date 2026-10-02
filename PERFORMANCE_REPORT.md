# Performance Report

## Measurement Notes

- Measurements were taken on 2026-10-02 against loopback HTTP servers, using disposable data directories and benchmark-only student accounts.
- This is the baseline of the current worktree, which already contains earlier local changes. No historical pre-change timings were available; none are inferred.
- Local timings exclude Internet, Render spin-up, Neon cold-start, and production data volume. Browser timing is from a headless browser on this workstation.
- UI was inspected but not changed for this baseline.

## Baseline

| Application / feature | Requests | API / render timing | Total duration | Sample |
|---|---:|---:|---:|---|
| StudySync login to student schedule ready | 12 same-origin | Login API median 90.2 ms; dashboard API 50.1 ms; DOMContentLoaded 99 ms; load 125.3 ms | 877 ms median (range 844-997 ms) | 5 browser trials for total; component timings from one browser run; APIs repeated 12/25 times |
| DongHanh login to Main ready | 4 same-origin | Login API median 98.6 ms; session API 5.3 ms; Main DOMContentLoaded 56.9 ms; load 109.1 ms | 323 ms | One browser run; API 12/15 requests |
| StudySync schedule save API | 10 successful requests | Median 14.9 ms; P95 19.1 ms | Not a page flow | Local JSON store; temporary student |
| StudySync assignment create API | 10 successful requests | Median 20.6 ms; P95 54.3 ms | Not a page flow | Local JSON store; temporary student |
| StudySync profile update API | 10 successful requests | Median 10.9 ms; P95 22.1 ms | Not a page flow | Local JSON store; temporary student |
| StudySync parent dashboard API | 25 requests | Median 7.6 ms; P95 12 ms | Not a page flow | Temporary parent with no linked children |
| StudySync owner APIs | 25 requests each | Overview median 3.2 ms/P95 6.2 ms; users median 4.9 ms/P95 7 ms | Not a page flow | Temporary owner and local JSON store |
| StudySync tab switch: schedule/assignments | No network requests | Median 7.2 ms; P95 12.5 ms from click to active view | Not a page flow | 20 browser interactions after final retry adjustment |
| OCR image import | Not measured | Not measured | Not measured | Local environment lacks OpenCV and RapidOCR; external OCR is intentionally excluded from the 1-second target |

## Current Test Baseline

- DongHanh: 26 passed.
- StudySync: 89 passed, 16 skipped.
- Parent-children endpoint now requires a parent bearer session and binds the query username to the authenticated parent.

## Bottlenecks Identified

1. StudySync login JavaScript waits a fixed 600 ms after successful authentication before navigating. The measured login-to-dashboard median is 877 ms, while the API login median is about 90 ms.
2. StudySync makes 12 same-origin requests from login click through dashboard readiness. The startup calls include push status, OCR availability, parent-link inbox, and dashboard data. Some are independent/background work.
3. DongHanh login-to-dashboard is 323 ms locally. PBKDF2 account verification accounts for most of the measured login API time; its cost will not be weakened.
4. Production Render/Neon latency was not benchmarked in this report; local numbers cannot predict cold-start or public-network latency.

## Changes

### Applied after baseline

- Removed the fixed 600 ms post-login timer; navigation starts immediately after successful authentication. No markup, text, styling, or auth behavior changed.
- Student and parent schedule/task dashboards refresh every 60 seconds while the page is visible and the user is not editing. Concurrent refreshes share one in-flight promise.
- Parent-link inbox and owner username-bot status are normal-priority data and refresh every 180 seconds. The link inbox only polls while Overview is visible; link actions still force an immediate refresh.
- Login and registration remain event-driven: they run on form submission, not on a background polling cycle.
- Secured `/api/parent/children` with session/role checks after the baseline exposed an unauthenticated data leak.
- No database indexes or schema changes were needed; local API timings were already below 55 ms P95 for the tested fixtures.

## Final Benchmark

| Feature | Before | After | Improvement |
|---|---:|---:|---:|
| StudySync login to schedule ready | 877 ms median, 12 requests | 240 ms median, 11 requests | 637 ms faster (72.6%); one fewer request |
| StudySync schedule/assignment tab switch | Not measured before | 7.2 ms median, 12.5 ms P95 | After-only measurement |

The five post-change login trials were 504, 222, 240, 375, and 221 ms. Inbox verification measured 0 inbox requests on initial schedule view and 1 request on entering Overview. Both browser probes reported zero console errors and zero failed requests. Component API times were not re-collected in the post-change run; the comparison is limited to total flow and request count.

## Regression

- UI redesign: none; no CSS or visual properties changed.
- Security: authentication, authorization, and password hashing remain enabled; parent-child listing now checks its session.
- Browser: StudySync login/dashboard and tab switching passed; zero console errors and failed requests.
- DongHanh tests: PASS (26/26).
- StudySync tests: PASS (89 passed, 16 skipped).

## Remaining Bottlenecks

- Public Render Free cold-start and Neon idle-compute latency are outside this loopback baseline.
- OCR image recognition is compute-heavy and external-service startup is outside the 1-second target.
- Local assignment/profile/parent/owner API timings are recorded above; production data-volume and hosted-service timings remain unmeasured.
- The earlier HTTP benchmark endpoint and test account ran against disposable local storage, not PostgreSQL or Render.
