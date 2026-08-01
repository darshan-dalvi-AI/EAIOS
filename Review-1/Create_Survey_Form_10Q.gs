/**
 * EAIOS — Primary Research Questionnaire (10 questions)
 *
 * A short form gets finished. Ten questions takes about three minutes, which
 * is the difference between 60 responses and 12 — and for a review panel, a
 * larger sample on ten sharp questions beats a thin sample on eighteen.
 *
 * Every question here tests one specific claim the project makes, so each
 * chart in the review answers a question somebody might ask:
 *
 *   Q1–Q2  Who answered — lets every later chart be split by role and company
 *          size, and shows whether the 50–500 target market was actually reached
 *   Q3–Q5  The problem is real and worth solving (time lost, where it hides,
 *          what today's tools get wrong)
 *   Q6     THE core claim — that an answer without a source is not good enough
 *   Q7     Why a private/self-hosted deployment matters
 *   Q8     Which of the twenty subsystems people actually want (prioritisation)
 *   Q9     The newest feature — simultaneous editing + in-browser execution
 *   Q10    Whether anyone would pay, which is what makes it a product
 *
 * Q3, Q6, Q7 and Q10 are the four that produce headline numbers. Q6 and Q7 are
 * 1–5 scales, so they give you a mean and a standard deviation rather than just
 * a bar chart — worth saying out loud in the review.
 *
 * ── HOW TO RUN (about 60 seconds) ─────────────────────────────────────────
 *   1. Go to  script.google.com  →  New project
 *   2. Delete the sample code, paste this whole file in
 *   3. Press Run (▶). Google asks you to authorise — this is your own script
 *      creating a file in your own Drive, so approve it.
 *      ("Google hasn't verified this app" → Advanced → Go to project.)
 *   4. Open  View → Logs.  The EDIT link and the SHARE link are printed there.
 *
 * A linked responses spreadsheet is created too, so the analysis tables in
 * 3_Primary_Research.docx can be filled straight from it.
 *
 * Running this twice creates two forms — delete the first from Drive if you
 * re-run it after editing.
 */

function createEaiosSurvey10() {
  var form = FormApp.create('EAIOS — How does your team find and trust company information?');

  form.setDescription(
    'A final-year engineering research survey (B.E. Computer Engineering, ' +
    'Vishwaniketan iMEET). We are studying how teams find information buried ' +
    'across documents, email and spreadsheets, and whether AI answers are ' +
    'trusted enough to act on.\n\n' +
    '10 questions, about 3 minutes. Responses are anonymous — we do not ask ' +
    'for your name, your employer, or any company data. Results are used only ' +
    'in an academic project report.');

  form.setProgressBar(true);
  form.setCollectEmail(false);         // anonymity is what gets honest answers
  form.setLimitOneResponsePerUser(false);
  form.setShowLinkToRespondAgain(false);
  form.setConfirmationMessage(
    'Thank you — your answers genuinely help. If you would like to see the ' +
    'finished platform, it is at eaios.onrender.com');

  // ── Q1 ── who is answering ─────────────────────────────────────────────
  form.addListItem()
    .setTitle('1. Which best describes your role?')
    .setHelpText('Used only to group answers — for example, whether managers ' +
                 'and engineers report the same frustrations.')
    .setChoiceValues([
      'Software engineer / developer',
      'Team lead / engineering manager',
      'Business / operations manager',
      'HR or people operations',
      'Finance or accounting',
      'Consultant / client-facing delivery',
      'Founder / business owner',
      'Student or academic',
      'Other',
    ])
    .setRequired(true);

  // ── Q2 ── does the target market hold up ───────────────────────────────
  form.addMultipleChoiceItem()
    .setTitle('2. How many people work at your organisation?')
    .setHelpText('This project targets mid-size organisations — the answers ' +
                 'here tell us whether that assumption was right.')
    .setChoiceValues([
      'Just me / freelance',
      '2–49',
      '50–200',
      '201–500',
      '501–2000',
      'More than 2000',
    ])
    .setRequired(true);

  // ── Q3 ── the problem, as a number ─────────────────────────────────────
  form.addMultipleChoiceItem()
    .setTitle('3. In a typical week, roughly how much time do you spend ' +
              'searching for information that already exists somewhere in ' +
              'your organisation?')
    .setHelpText('Hunting through documents, drives, email threads or ' +
                 'spreadsheets — or asking a colleague because it is faster ' +
                 'than looking.')
    .setChoiceValues([
      'Less than 1 hour',
      '1–3 hours',
      '3–5 hours',
      '5–10 hours',
      'More than 10 hours',
    ])
    .setRequired(true);

  // ── Q4 ── validates multi-source ingestion ─────────────────────────────
  form.addCheckboxItem()
    .setTitle('4. Where does that information usually live? (select all that apply)')
    .setChoiceValues([
      'PDF documents',
      'Word documents',
      'Spreadsheets (Excel / Google Sheets)',
      'Presentations',
      'Email threads',
      'Chat messages (Slack, Teams, WhatsApp)',
      'Scanned images or photographed documents',
      'A wiki or internal site',
      'Only in a colleague’s head',
    ])
    .showOtherOption(true)
    .setRequired(true);

  // ── Q5 ── what today's tools get wrong ─────────────────────────────────
  form.addMultipleChoiceItem()
    .setTitle('5. If you have used an AI assistant (ChatGPT, Copilot, Gemini ' +
              'or similar) for work, what has been the single biggest problem?')
    .setChoiceValues([
      'It does not know anything about my company’s own documents',
      'I cannot tell whether the answer is true',
      'It states things confidently that turn out to be wrong',
      'I am not allowed, or not comfortable, uploading company files to it',
      'It is too expensive per person',
      'No real problem — it works well for me',
      'I have not used one for work',
    ])
    .showOtherOption(true)
    .setRequired(true);

  // ── Q6 ── THE core claim of the project ────────────────────────────────
  form.addScaleItem()
    .setTitle('6. How important is it that an AI answer shows you the exact ' +
              'source it came from, so you can check it yourself?')
    .setHelpText('For example: the answer names the document and the section, ' +
                 'and one click opens it at that spot.')
    .setBounds(1, 5)
    .setLabels('Not important', 'Essential')
    .setRequired(true);

  // ── Q7 ── why private / self-hosted matters ────────────────────────────
  form.addScaleItem()
    .setTitle('7. How concerned would you be about your company’s ' +
              'documents being sent to an external AI provider to be answered?')
    .setBounds(1, 5)
    .setLabels('Not concerned', 'Very concerned')
    .setRequired(true);

  // ── Q8 ── which of the twenty subsystems people actually want ──────────
  // The cap is enforced, not just requested. A "pick up to 4" question with no
  // validation is one where a third of people tick everything, and a feature
  // ranking built on that says nothing — every option scores ~80%.
  form.addCheckboxItem()
    .setTitle('8. Which of these would be genuinely useful to your team? ' +
              '(select up to 4)')
    .setHelpText('Pick what you would actually use, not what sounds impressive.')
    .setChoiceValues([
      'Ask a question and get an answer with citations from our own documents',
      'One search across documents, email and spreadsheets at once',
      'Ask questions of data inside spreadsheets and tables in plain English',
      'Charts and dashboards described in plain English instead of built by hand',
      'Meeting notes turned into minutes and task cards automatically',
      'A code editor several people can type in at the same time',
      'Automations that trigger when a document is uploaded',
      'An audit trail of every AI answer and who accessed what',
    ])
    .showOtherOption(true)
    .setValidation(FormApp.createCheckboxValidation()
                          .setHelpText('Please choose at most 4.')
                          .requireSelectAtMost(4)
                          .build())
    .setRequired(true);

  // ── Q9 ── the newest feature ───────────────────────────────────────────
  form.addMultipleChoiceItem()
    .setTitle('9. Would your team use a shared code editor where several ' +
              'people can edit the same file at the same time, and run the ' +
              'code straight in the browser?')
    .setHelpText('Like Google Docs, but for code — with the output appearing ' +
                 'without installing anything.')
    .setChoiceValues([
      'Yes — we would use it regularly',
      'Yes — occasionally, for reviews or pair work',
      'Maybe, if it worked with our existing tools',
      'No — we are happy with our current editors',
      'Not relevant — my team does not write code',
    ])
    .setRequired(true);

  // ── Q10 ── would anyone pay ────────────────────────────────────────────
  form.addMultipleChoiceItem()
    .setTitle('10. If a private version of this ran entirely on your own ' +
              'company’s server, what would your organisation realistically ' +
              'pay per person per month?')
    .setHelpText('An honest low answer is more useful to us than a polite high one.')
    .setChoiceValues([
      'Nothing — only if it were free or open source',
      'Under ₹400 (about $5)',
      '₹400–₹850 (about $5–$10)',
      '₹850–₹1700 (about $10–$20)',
      'More than ₹1700 (about $20+)',
      'I am not the person who decides that',
    ])
    .setRequired(true);

  // ── linked responses spreadsheet ───────────────────────────────────────
  // Created explicitly rather than left to Google's "create spreadsheet"
  // button, so the file has a predictable name to cite in the report.
  var sheet = SpreadsheetApp.create('EAIOS — Primary Research Responses (10Q)');
  form.setDestination(FormApp.DestinationType.SPREADSHEET, sheet.getId());

  Logger.log('==============================================================');
  Logger.log('  EDIT the form:   %s', form.getEditUrl());
  Logger.log('  SHARE this link: %s', form.getPublishedUrl());
  Logger.log('  RESPONSES sheet: %s', sheet.getUrl());
  Logger.log('==============================================================');
  Logger.log('Aim for 30+ responses. Below about 30 the percentages move too');
  Logger.log('much for one extra answer, and a reviewer may fairly say so.');
}
