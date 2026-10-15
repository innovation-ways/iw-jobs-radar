const LINK = 'underline'

function Ext({ href, children }: { href: string; children: string }) {
  return (
    <a className={LINK} href={href} target="_blank" rel="noreferrer noopener">
      {children}
    </a>
  )
}

/**
 * About & credits: where the data comes from and under which licence, what stays on this machine
 * and the known limitations of this version. Attribution required by the data licences lives here
 * and next to the data it covers.
 */
export function About() {
  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-4 px-4 sm:px-6 py-6 text-sm">
      <section className="rounded-lg border border-line bg-surface p-4">
        <h2 className="text-sm font-semibold">Jobs Radar</h2>
        <p className="mt-2 text-ink-2">
          A personal job-market radar. It collects jobs from permitted public sources, scores them
          against your profile and search intent, and keeps your decisions. Everything you enter
          stays on this machine; nothing is sent to a remote AI provider without your confirmation
          for each CV, and job text is only analysed by a local model.
        </p>
      </section>

      <section aria-labelledby="credits" className="rounded-lg border border-line bg-surface p-4">
        <h2 id="credits" className="sr-only">
          Data credits
        </h2>
        <h3 className="text-sm font-semibold">Data credits</h3>
        <ul className="mt-2 flex flex-col gap-2 text-ink-2">
          <li>
            Place data from <Ext href="https://www.geonames.org">GeoNames</Ext>, used under{' '}
            <Ext href="https://creativecommons.org/licenses/by/4.0/">CC BY 4.0</Ext>.
          </li>
          <li>
            Company facts from <Ext href="https://www.wikidata.org">Wikidata</Ext> (CC0 1.0) and
            legal entities from <Ext href="https://www.gleif.org">GLEIF</Ext> (CC0 1.0).
          </li>
          <li>
            Company descriptions from <Ext href="https://www.wikipedia.org">Wikipedia</Ext>,
            available under{' '}
            <Ext href="https://creativecommons.org/licenses/by-sa/4.0/">CC BY-SA 4.0</Ext>; each
            description links to its article.
          </li>
          <li>
            Technology hints from public <Ext href="https://github.com">GitHub</Ext> organisation
            pages.
          </li>
          <li>
            Job postings from public job-board APIs such as{' '}
            <Ext href="https://www.greenhouse.com">Greenhouse</Ext>; each posting links back to its
            source.
          </li>
          <li>
            Job boards you add: <Ext href="https://www.arbeitnow.com">Arbeitnow</Ext>,{' '}
            <Ext href="https://jobicy.com">Jobicy</Ext>,{' '}
            <Ext href="https://himalayas.app">Himalayas</Ext>,{' '}
            <Ext href="https://weworkremotely.com">We Work Remotely</Ext>,{' '}
            <Ext href="https://www.workingnomads.com">Working Nomads</Ext>,{' '}
            <Ext href="https://remoteok.com">Remote OK</Ext>,{' '}
            <Ext href="https://www.freelancermap.com">freelancermap</Ext>,{' '}
            <Ext href="https://remotive.com">Remotive</Ext> and{' '}
            <Ext href="https://www.itjobs.pt">ITJobs.pt</Ext>. Each posting shows which board it
            came from and links back to it.
          </li>
        </ul>
      </section>

      <section aria-labelledby="limits" className="rounded-lg border border-line bg-surface p-4">
        <h2 id="limits" className="sr-only">
          Known limitations
        </h2>
        <h3 className="text-sm font-semibold">Known limitations</h3>
        <ul className="mt-2 list-disc pl-5 text-ink-2">
          <li>
            There is no authentication in this version: keep the app on this machine or a trusted
            network.
          </li>
          <li>A fit score explains how a job matches what you said; it does not predict hiring.</li>
          <li>Scanned PDFs cannot be read (no OCR): save the CV with text or as a .txt file.</li>
          <li>Pay is compared in the same currency only; there is no currency conversion yet.</li>
          <li>
            Small local models can miss details: every extraction keeps its quotes so you can check.
          </li>
          <li>
            Trend history starts when collection started; longer periods unlock as data accumulates.
          </li>
        </ul>
      </section>
    </div>
  )
}
