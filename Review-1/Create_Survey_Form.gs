/**
 * EAIOS — Primary Research Questionnaire
 * Builds the 18-item survey from 3_Primary_Research.docx as a live Google Form.
 *
 * ── HOW TO RUN (about 60 seconds) ─────────────────────────────────────────
 *   1. Go to  script.google.com  →  New project
 *   2. Delete the sample code, paste this whole file in
 *   3. Press Run (▶). Google will ask you to authorise — it is your own
 *      script creating a file in your own Drive, so approve it.
 *      ("Google hasn't verified this app" → Advanced → Go to project.)
 *   4. Open View → Logs. The form's EDIT link and SHARE link are printed there.
 *
 * It also creates a linked responses spreadsheet, so the analysis tables in
 * §5 of the Primary Research document can be filled straight from it.
 *
 * Running this twice creates two forms. Delete the first from Drive if you
 * re-run it after editing.
 */

function createEaiosSurvey() {
  var form = FormApp.create('EAIOS — AI Adoption, Trust and Information Retrieval');

  form.setDescription(
    'This short survey supports a final-year Computer Engineering major project at ' +
    'Vishwaniketan iMEET (University of Mumbai) on enterprise AI assistants.\n\n' +
    'It takes about 5 minutes and has 18 questions.\n\n' +
    'Participation is voluntary and completely anonymous. No name, email address or ' +
    'other identifying information is collected, and responses are reported only in ' +
    'aggregate. You may stop at any point.\n\n' +
    'Thank you for your time.');

  // Anonymous by design — this is the ethics commitment in the methodology
  // table, so it is set in code rather than left to a checkbox someone might
  // forget. Each setter is applied individually: Google has been migrating
  // these APIs, and one deprecated method throwing must not abort the script
  // and leave a half-built form behind.
  applySettings(form, {
    'setCollectEmail': false,             // no email address recorded
    'setLimitOneResponsePerUser': false,  // no Google sign-in required to reply
    'setProgressBar': true,
    'setAllowResponseEdits': false,
    'setShowLinkToRespondAgain': false,
    'setConfirmationMessage': 'Thank you — your response has been recorded anonymously.'
  });

  var LIKERT = 5;

  /* ── Section A — Respondent Profile ─────────────────────────────────── */
  section(form, 'Section A — Respondent Profile',
          'A few questions about your context, so answers can be compared across groups.');

  choice(form, 'Q1. Which best describes your current role?', [
    'Student (final year / postgraduate)',
    'Faculty or academic staff',
    'Software engineer / IT professional',
    'Manager or team lead',
    'Administrative or operations staff'
  ], { other: true });

  choice(form, 'Q2. What is the approximate size of your organisation or institution?', [
    'Fewer than 50 people',
    '50–250 people',
    '251–1000 people',
    'More than 1000 people'
  ]);

  choice(form, 'Q3. How often do you use AI assistants (ChatGPT, Copilot, Gemini, Claude) ' +
               'in your work or study?', [
    'Daily',
    'A few times a week',
    'A few times a month',
    'Rarely',
    'Never'
  ]);

  /* ── Section B — The Information-Retrieval Problem ──────────────────── */
  section(form, 'Section B — Finding Information',
          'About locating information that already exists inside your organisation.');

  choice(form, 'Q4. In a typical week, roughly how much time do you spend searching for ' +
               'information that already exists somewhere in your organisation\'s documents?', [
    'Less than 1 hour',
    '1–3 hours',
    '3–5 hours',
    '5–10 hours',
    'More than 10 hours'
  ]);

  checkboxes(form, 'Q5. Where does the information you need usually live?', [
    'Email',
    'Shared drives / cloud storage',
    'Spreadsheets',
    'PDF reports and contracts',
    'Chat applications',
    'Internal wiki or portal',
    'Colleagues\' personal knowledge'
  ], 'Select all that apply.');

  scale(form, 'Q6. How often does the following occur: you cannot find a document you ' +
              'know exists?', 'Never', 'Very often');

  scale(form, 'Q7. How often do you re-create a document or analysis because you could ' +
              'not locate the original?', 'Never', 'Very often');

  /* ── Section C — Trust, Grounding and Citation ──────────────────────── */
  // Q9 and Q10 are deliberately adjacent and deliberately identical except for
  // the citation. The gap between them is the survey's key measurement, so the
  // order must not be shuffled.
  section(form, 'Section C — Trust in AI Answers',
          'Please answer Q9 and Q10 in the order shown.');

  scale(form, 'Q8. How much do you trust answers produced by a general AI assistant ' +
              'about your organisation\'s internal matters?', 'Not at all', 'Completely');

  scale(form, 'Q9. An AI system gives you an answer with NO source reference. How willing ' +
              'are you to act on it in a work context?',
        'Not at all willing', 'Very willing');

  scale(form, 'Q10. The same answer now cites the exact document and section it came from, ' +
              'with a confidence score. How willing are you to act on it?',
        'Not at all willing', 'Very willing');

  choice(form, 'Q11. Have you ever received a confidently stated but factually wrong ' +
               'answer from an AI tool?', [
    'Yes, more than once',
    'Yes, once',
    'No',
    'Not sure'
  ]);

  /* ── Section D — Data Isolation and Confidentiality ─────────────────── */
  section(form, 'Section D — Confidentiality', '');

  scale(form, 'Q12. How concerned would you be about uploading your organisation\'s ' +
              'internal documents to a shared cloud AI platform?',
        'Not concerned', 'Extremely concerned');

  scale(form, 'Q13. How important is a guarantee that no other organisation using the ' +
              'same platform can ever see your data?',
        'Not important', 'Critically important');

  choice(form, 'Q14. Which assurance would most increase your confidence in such a platform?', [
    'Independent security audit and published findings',
    'Isolation enforced by the database, not just application code',
    'Complete audit trail of every access',
    'On-premise or self-hosted deployment option',
    'Recognised compliance certification'
  ]);

  /* ── Section E — Capability Prioritisation ──────────────────────────── */
  section(form, 'Section E — Which Capabilities Matter', '');

  // Google Forms has no ranking question type. A grid with one column per rank
  // is the standard substitute: it produces the same ordinal data and charts
  // the same way. Forms cannot enforce "use each number once", so the help text
  // asks for it and the analysis should drop any row that duplicates a rank.
  form.addGridItem()
      .setTitle('Q15. Rank these capabilities from most to least useful for your work.')
      .setHelpText('1 = most useful, 6 = least useful. Please use each number only once.')
      .setRows([
        'Ask questions of internal documents and receive cited answers',
        'Ask questions of spreadsheet/tabular data in plain English',
        'Search across email, files and chat from one place',
        'Automatic meeting minutes and action items',
        'Custom AI assistants configured for a specific team',
        'Automated workflows triggered by document uploads'
      ])
      .setColumns(['1', '2', '3', '4', '5', '6'])
      .setRequired(true);

  scale(form, 'Q16. How valuable would a single unified interface be, compared with ' +
              'separate tools for each of the above?',
        'Not valuable', 'Extremely valuable');

  /* ── Section F — Barriers and Open Feedback ─────────────────────────── */
  section(form, 'Section F — Barriers', '');

  choice(form, 'Q17. What is the single biggest barrier to adopting AI tools in your ' +
               'organisation?', [
    'Data privacy and confidentiality concerns',
    'Accuracy and reliability of answers',
    'Cost',
    'Lack of training or familiarity',
    'Integration with existing systems',
    'Organisational or policy restrictions'
  ]);

  // The only optional question. Making a free-text box mandatory is the fastest
  // way to lose respondents at the last step.
  form.addParagraphTextItem()
      .setTitle('Q18. What would make you personally trust and adopt an internal AI assistant?')
      .setHelpText('Optional — but the most useful answer in the survey.')
      .setRequired(false);

  /* ── Responses spreadsheet ──────────────────────────────────────────── */
  var sheet = SpreadsheetApp.create('EAIOS Survey — Responses');
  form.setDestination(FormApp.DestinationType.SPREADSHEET, sheet.getId());

  Logger.log('════════════════════════════════════════════════════════');
  Logger.log('SHARE THIS LINK:  %s', form.getPublishedUrl());
  Logger.log('EDIT THE FORM:    %s', form.getEditUrl());
  Logger.log('RESPONSES SHEET:  %s', sheet.getUrl());
  Logger.log('════════════════════════════════════════════════════════');
  Logger.log('%s questions created. Target: 40 minimum, 60+ preferred.',
             form.getItems().length - 6);   // minus the 6 section breaks
}

/* ── small helpers, so the questions above read like the document ─────── */

function section(form, title, help) {
  form.addPageBreakItem().setTitle(title).setHelpText(help || '');
}

function choice(form, title, options, opts) {
  var item = form.addMultipleChoiceItem()
                 .setTitle(title)
                 .setChoiceValues(options)
                 .setRequired(true);
  if (opts && opts.other) item.showOtherOption(true);
  return item;
}

function checkboxes(form, title, options, help) {
  return form.addCheckboxItem()
             .setTitle(title)
             .setHelpText(help || '')
             .setChoiceValues(options)
             .setRequired(true);
}

function scale(form, title, lowLabel, highLabel) {
  return form.addScaleItem()
             .setTitle(title)
             .setBounds(1, 5)
             .setLabels(lowLabel, highLabel)
             .setRequired(true);
}
