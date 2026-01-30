import puppeteer from 'puppeteer';

const browser = await puppeteer.launch({ headless: 'new' });
const page = await browser.newPage();
await page.goto('https://lemma.id');

const h1 = await page.$eval('h1', el => el.textContent);
const title = await page.title();
const subhead = await page.$eval('.hero p:nth-child(2)', el => el.textContent).catch(() => 'N/A');
const buttons = await page.$$eval('#hero-buttons .btn', btns => btns.map(b => b.textContent.trim()));

console.log('=== NEW HERO CHECK ===');
console.log('Page Title:', title);
console.log('Hero H1:', h1.trim());
console.log('CTA Buttons:', buttons.join(' | '));
console.log('======================');

await browser.close();
