# StoreSense report: submission checklist

Open items for `reports/StoreSense_DMDW_Project_Report.md` (and its PDF). This list is kept out of the report itself.
Rebuild the PDF and Word file after any change: `python reports/build_pdf.py`.

**Administrative details**

- [x] Full names and roll numbers of all six members (filled in on 15 Oct 2026; Kartik Biswal is taken to be @KB-0141).
- [x] Faculty guide, school, institution, place, academic year and submission date.
- [x] Certificate, declaration and acknowledgement pages removed, as asked.
- [ ] Confirm the guide's school: the title page says "School of Computer Engineering" for the guide and "School of Computer Science and Engineering" for the team, as given.
- [ ] Confirm the academic year (2026–27 is inferred from the submission date).

**Team contribution (Chapter 12)**

- [ ] Each member checks and corrects their own subsection in 12.4, adding work done outside GitHub.
- [ ] The team agrees on, or replaces, the **provisional** percentages in 12.5.
- [ ] Whether pull requests were reviewed (none is recorded on GitHub), and by whom.
- [ ] Who wrote the task briefs and the result-file contract in `handoff/`.
- [ ] Why @DIO4699 does not appear in the repository's collaborator list.
- [ ] Who compiled this submission report (row in Table 12.2).
- [ ] Final presentation assignments (12.9); `docs/DEMO_FLOW.md` says "five presenters" but lists six.
- [ ] **Use of AI-assisted tools.** The declaration page that held this statement was removed. If the institution requires disclosure, add a short note (for example in the Introduction or at the end of Chapter 12) saying which tools were used and for which parts of the code and report.
- [ ] Once the above is settled, remove the "To confirm" labels from Chapter 12.

**Evidence and results**

- [x] Dashboard screenshots added in Section 9.6 (Figures 9.1–9.6, taken 15 Oct 2026).
- [x] Manual browser check of each page (TC-37), done with those screenshots.
- [ ] Confirm the **hosted app URL** and that it works (TC-38), or remove the hosting claim.
- [ ] Explain or reconcile the two recorded full-load times (8.6 s in section 1, 13.8 s in section 2 of the technical report).
- [ ] Record the specification of the machine used for the full-data runs (it would replace the recommendations in Table 4.3).
- [ ] Optionally investigate the 2 warnings of the test run.
- [ ] Decide whether to commit `handoff/PHASE4_SHARED_CONTRACT.md`: `dashboard/data.py` and the technical report refer to it, but it is excluded from git.
- [ ] Give evaluators access to the private repository, if they need it.

**Formatting**

- [x] Typeset PDF with cover, contents and lists with page numbers (`python reports/build_pdf.py`).
- [ ] Mermaid diagrams do not render in Microsoft Word. If you submit the Word file instead of the PDF, export each diagram as an image and insert it in place of its code block.
- [ ] Verify the references marked "(verify)", especially the web URLs and [9].
- [ ] Slides for the presentation are not in the repository; prepare them separately.
