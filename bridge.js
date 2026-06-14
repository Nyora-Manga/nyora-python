import fs from 'fs';
import path from 'path';
import { JSDOM } from 'jsdom';

const BUNDLE_URL = 'https://Hasan72341.github.io/nyora-ota-parsers/parsers.bundle.js';
const BUNDLE_PATH = './parsers.bundle.js';
const BROWSER_UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36';

async function fetchBundleIfNeeded() {
    if (!fs.existsSync(BUNDLE_PATH)) {
        console.warn('Downloading parsers.bundle.js...');
        const res = await fetch(BUNDLE_URL);
        if (!res.ok) throw new Error(`Failed to fetch bundle: ${res.statusText}`);
        const code = await res.text();
        fs.writeFileSync(BUNDLE_PATH, code, 'utf-8');
    }
}

async function run() {
    await fetchBundleIfNeeded();

    // Read input arguments from stdin
    const inputData = fs.readFileSync(0, 'utf-8');
    const { sourceId, method, args } = JSON.parse(inputData);

    const bundleCode = fs.readFileSync(BUNDLE_PATH, 'utf-8');

    // Create a JSDOM context to mock browser globals
    const dom = new JSDOM('<!DOCTYPE html><html><head></head><body></body></html>', {
        url: 'https://example.com'
    });

    const window = dom.window;
    const document = window.document;

    // Domain overrides tracking
    let domainOverrides = {};
    let lastFinalUrl = '';

    // Polyfills and prelude mimicking JavaScriptExtensionService.kt
    const context = {
        httpGet: async function(url, parser) {
            const domain = parser?.domain || '';
            const origin = domain ? `https://${domain}` : '';
            const headers = {
                'User-Agent': BROWSER_UA,
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'identity',
                'Cache-Control': 'no-cache',
            };
            if (origin) headers['Referer'] = origin + '/';

            const response = await fetch(url, { headers });
            lastFinalUrl = response.url;
            
            // Handle redirects
            if (parser && response.url) {
                try {
                    const fd = new URL(response.url).hostname;
                    const od = new URL(url).hostname;
                    if (fd && od && fd !== od) {
                        parser.domain = fd;
                        domainOverrides[sourceId] = fd;
                    }
                } catch(e) {}
            }

            return await response.text();
        },
        httpPost: async function(url, body, extraHeaders, parser) {
            const domain = parser?.domain || '';
            const origin = domain ? `https://${domain}` : '';
            const headers = {
                'User-Agent': BROWSER_UA,
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'identity',
                'Cache-Control': 'no-cache',
                'Content-Type': 'application/x-www-form-urlencoded',
                'X-Requested-With': 'XMLHttpRequest'
            };
            if (origin) {
                headers['Referer'] = origin + '/';
                headers['Origin'] = origin;
            }
            if (extraHeaders) {
                Object.assign(headers, extraHeaders);
            }

            const response = await fetch(url, {
                method: 'POST',
                headers,
                body: body || ''
            });
            lastFinalUrl = response.url;

            // Handle redirects
            if (parser && response.url) {
                try {
                    const fd = new URL(response.url).hostname;
                    const od = new URL(url).hostname;
                    if (fd && od && fd !== od) {
                        parser.domain = fd;
                        domainOverrides[sourceId] = fd;
                    }
                } catch(e) {}
            }

            return await response.text();
        },
        parseHTML: function(html) {
            const parseDom = new JSDOM(html);
            // We return the documentElement directly. In standard browsers,
            // this has all querySelector/querySelectorAll/childNodes etc.
            return parseDom.window.document.documentElement;
        },
        decodeContent: function(s) {
            return s;
        }
    };

    // Expose context to global window
    window.__context = context;
    window.__domainOverrides = domainOverrides;

    // Evaluate the bundle in window context
    const runInContext = new Function('window', 'console', `${bundleCode}; return NyoraParsers;`);
    const NyoraParsers = runInContext(window, console);

    const cleanSourceId = sourceId.replace('parser:', '');
    const p = NyoraParsers.getParser(cleanSourceId, context);
    if (!p) {
        throw new Error(`Parser not found: ${cleanSourceId}`);
    }

    let result;
    if (method === 'list') {
        const page = args.page || 1;
        const order = args.order || 'POPULARITY';
        const filter = args.filter || {};
        result = await p.getListPage(page, order, filter);
    } else if (method === 'details') {
        result = await p.getDetails({ id: args.url, url: args.url, source: { id: cleanSourceId, name: cleanSourceId } });
    } else if (method === 'pages') {
        result = await p.getPages({ id: args.url, url: args.url, branch: args.branch, source: { id: cleanSourceId } });
    } else {
        throw new Error(`Unknown method: ${method}`);
    }

    console.log(JSON.stringify(result, null, 2));
}

run().catch(err => {
    console.error(err);
    process.exit(1);
});
