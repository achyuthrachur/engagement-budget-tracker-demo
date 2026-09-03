import { Fragment, useEffect } from "react";
import { AppShell } from "../components/AppShell";

const JUMPS = [
  ["#setup", "Set up the tracker"],
  ["#engagement", "Create an engagement"],
  ["#weekly", "Run the weekly budget"],
  ["#recovery", "Correct a mistake"],
  ["#glossary", "Understand the terms"],
];

const SECTIONS = [
  {
    id: "setup",
    step: "01",
    title: "Set up the tracker",
    items: [
      "Open Settings.",
      "Review the role rate card.",
      "Enter engagement and contract discounts as normal percentages.",
      "Confirm variance thresholds.",
      "Select Save settings.",
      "Create a recovery backup.",
    ],
  },
  {
    id: "engagement",
    step: "02",
    title: "Create an engagement",
    items: [
      "Select New engagement.",
      "Use the exact Cognos project identifier as the engagement code.",
      "Choose Simple for one overall budget or Complex for phase and weekly planning.",
      "Add every expected worker using the exact Cognos “Last, First” name.",
      "Verify rates and offshore status.",
      "For Complex mode, add every phase and its signed statement of work budget.",
      "Set phase target hours, distribute across weeks and make every reconciliation difference zero.",
      "Read and select the baseline confirmation, then create the engagement.",
    ],
  },
  {
    id: "weekly",
    step: "03",
    title: "Run the weekly budget",
    items: [
      "Create a recovery backup in Settings.",
      "Export the raw Time and Cost Detail workbook from Cognos.",
      "Open the engagement and select Weekly import.",
      "Choose the file and select Preview import.",
      "Resolve unknown workers, project mismatches and unmatched phases.",
      "Review variance warnings and selected totals.",
      "Select Review and commit import. The tracker creates another recovery backup.",
      "Return to each phase and update future Forecast values.",
      "Review Overview, then select Export to create the partner report.",
    ],
  },
  {
    id: "recovery",
    step: "04",
    title: "Correct a mistake",
    paragraph:
      "For a bad import, open History and delete only the affected snapshot. The tracker backs up first. Preview and commit the corrected Cognos file. For a larger problem, use Settings to validate and restore a database backup.",
  },
];

const GLOSSARY = [
  ["Statement of work budget", "The signed fee budget for the work."],
  ["Standard rate", "The internal value of a person’s time."],
  ["Engagement rate", "The rate used for engagement planned fees."],
  ["Contract rate", "The rate reported by Cognos and compared with the statement of work budget."],
  ["Advance billing tracking", "Informational tracking that does not enforce the budget."],
  ["Realization", "Effective statement of work budget less Crowe-paid expenses, divided by actual standard fees."],
  ["Approved budget addition", "An engagement-wide approved budget increase."],
  ["Approved budget reduction", "An approved budget decrease that requires an explanation."],
  ["Change order", "An approved addition assigned to a specific phase."],
  ["Budget, Actual and Forecast", "The approved baseline, imported Cognos time and future estimate."],
];

export default function Help() {
  // The route is a full navigation (see app.py), so the browser's built-in
  // scroll-to-fragment runs before React has rendered anything to scroll to.
  useEffect(() => {
    if (window.location.hash) {
      document.getElementById(window.location.hash.slice(1))?.scrollIntoView();
    }
  }, []);

  return (
    <AppShell>
      <div className="topbar">
        <div className="topbar-inner">
          <div className="topbar-title">
            <span className="topbar-client">Help and operating guide</span>
            <span className="topbar-meta">Engagement Budget Tracker</span>
          </div>
        </div>
      </div>

      <div className="page-body">
        <section className="help-hero">
          <div>
            <span className="eyebrow">Engagement Budget Tracker</span>
            <h2>Choose what you need to do</h2>
            <p>These instructions use the same words and buttons you will see in the tracker.</p>
          </div>
          <nav className="help-jumps">
            {JUMPS.map(([href, label]) => (
              <a key={href} href={href}>
                {label}
              </a>
            ))}
          </nav>
        </section>

        {SECTIONS.map((section) => (
          <section className="help-section" id={section.id} key={section.id}>
            <span className="step-number">{section.step}</span>
            <div>
              <h2>{section.title}</h2>
              {section.paragraph ? (
                <p>{section.paragraph}</p>
              ) : (
                <ol>
                  {section.items.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ol>
              )}
            </div>
          </section>
        ))}

        <section className="help-section glossary" id="glossary">
          <span className="step-number">05</span>
          <div>
            <h2>Glossary</h2>
            <dl>
              {GLOSSARY.map(([term, definition]) => (
                <Fragment key={term}>
                  <dt>{term}</dt>
                  <dd>{definition}</dd>
                </Fragment>
              ))}
            </dl>
          </div>
        </section>
      </div>
    </AppShell>
  );
}
