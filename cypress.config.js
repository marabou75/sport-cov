// cypress.config.js
const { defineConfig } = require('cypress');
const { ImapFlow } = require('imapflow');
const { simpleParser } = require('mailparser');

/**
 * Récupère le dernier OTP Gmail arrivé APRÈS sinceTs.
 */
async function getOtpGmail({ user, appPassword, sinceTs, timeoutMs = 120000 }) {
  if (!user || !appPassword) {
    throw new Error('GMAIL_USER / GMAIL_APP_PASSWORD manquants');
  }

  const client = new ImapFlow({
    host: 'imap.gmail.com',
    port: 993,
    secure: true,
    auth: {
      user: String(user).trim(),
      pass: String(appPassword).replace(/\s+/g, ''), // retire tout espace
    },
    logger: true, // utile pour diagnostiquer
  });

  const codeRe = /(?<!\d)(\d{5,8})(?!\d)/;
  const since = sinceTs ? new Date(sinceTs) : new Date(Date.now() - 5 * 60 * 1000);
  const deadline = Date.now() + timeoutMs;

  await client.connect();
  await client.mailboxOpen('INBOX');

  async function extract(uid) {
    const msg = await client.fetchOne(uid, { envelope: true, source: true });
    const subject = msg?.envelope?.subject || '';
    let m = subject.match(codeRe);

    if (!m && msg?.source) {
      const parsed = await simpleParser(msg.source);
      const text =
        (parsed.text || '') +
        ' ' +
        (parsed.html ? parsed.html.replace(/<[^>]+>/g, ' ') : '');
      m = text.match(codeRe);
    }
    return m?.[1] || null;
  }

  try {
    while (Date.now() < deadline) {
      // Mails arrivés après sinceTs uniquement
      const uids = await client.search({
        since,
        from: 'no-reply@auth.appnotify.io', // adapte si besoin
      });

      if (uids.length) {
        // On prend le + récent
        const uid = Math.max(...uids);
        const code = await extract(uid);
        if (code) return code;

        // Fallback : Tous les messages (si classement bouge côté Gmail)
        try {
          await client.mailboxOpen('[Gmail]/Tous les messages');
          const all = await client.search({ since, from: 'no-reply@auth.appnotify.io' });
          if (all.length) {
            const uid2 = Math.max(...all);
            const code2 = await extract(uid2);
            if (code2) return code2;
          }
          await client.mailboxOpen('INBOX');
        } catch {
          // label absent : on ignore
        }
      }

      await new Promise((r) => setTimeout(r, 1200));
    }
    throw new Error('OTP non reçu via Gmail (timeout)');
  } finally {
    try { await client.logout(); } catch {}
  }
}

module.exports = defineConfig({
  e2e: {
    baseUrl: process.env.CYPRESS_BASE_URL || 'https://sport-cov.glide.page',
    supportFile: 'cypress/support/e2e.js',
    specPattern: 'cypress/e2e/**/*.cy.{js,jsx,ts,tsx}',
    // (optionnel) augmente un peu les délais par défaut
    defaultCommandTimeout: 15000,
    pageLoadTimeout: 60000,
    video: false,

    setupNodeEvents(on, config) {
      on('task', {
        getOtpGmail(args) {
          return getOtpGmail(args || {});
        },
        // Alias rétro-compat si besoin
        'otp:waitForLatest': (args) => getOtpGmail(args || {}),
      });

      return config;
    },
  },
});
