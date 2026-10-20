#!/usr/bin/env node
/**
 * generate-openspec-skills.js
 *
 * Regenerate academy/skills/openspec-* SKILL.md files from the installed
 * @fission-ai/openspec package's template API.
 *
 * Usage:
 *   npm install -g @fission-ai/openspec@<version>
 *   node scripts/generate-openspec-skills.js
 *
 * The script reads the installed package version, generates each skill's
 * SKILL.md from the zero-arity template getters, preserves allowed-tools
 * from the existing files, and writes the updated files.
 */

const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

// Resolve the installed @fission-ai/openspec package
const pkgRoot = execSync('npm root -g', { encoding: 'utf8' }).trim();
const openspecRoot = path.join(pkgRoot, '@fission-ai', 'openspec');
const pkgJson = JSON.parse(fs.readFileSync(path.join(openspecRoot, 'package.json'), 'utf8'));
const version = pkgJson.version;

console.log(`Generating skills from @fission-ai/openspec@${version}`);

const templates = require(path.join(openspecRoot, 'dist', 'core', 'templates', 'skill-templates.js'));

// Map: skill directory name -> template getter function name
const SKILL_MAP = {
  'openspec-explore':        'getExploreSkillTemplate',
  'openspec-propose':        'getOpsxProposeSkillTemplate',
  'openspec-update-change':  'getUpdateChangeSkillTemplate',
  'openspec-apply-change':   'getApplyChangeSkillTemplate',
  'openspec-sync-specs':     'getSyncSpecsSkillTemplate',
  'openspec-archive-change': 'getArchiveChangeSkillTemplate',
};

// Repo root is two levels up from this script
const repoRoot = path.resolve(__dirname, '..');
const skillsBase = path.join(repoRoot, 'academy', 'skills');

let updatedCount = 0;

for (const [skillName, fnName] of Object.entries(SKILL_MAP)) {
  const skillDir = path.join(skillsBase, skillName);
  const skillFile = path.join(skillDir, 'SKILL.md');

  if (!templates[fnName]) {
    console.error(`  ERROR: template function ${fnName} not found in package`);
    process.exit(1);
  }

  const tmpl = templates[fnName]();
  if (!tmpl || !tmpl.instructions) {
    console.error(`  ERROR: ${fnName}() returned empty content`);
    process.exit(1);
  }

  // Read existing file to preserve allowed-tools
  let allowedTools = 'Bash(openspec:*)';
  if (fs.existsSync(skillFile)) {
    const existing = fs.readFileSync(skillFile, 'utf8');
    const match = existing.match(/^allowed-tools:\s*(.+)$/m);
    if (match) allowedTools = match[1].trim();
  }

  // Assemble SKILL.md
  const content = [
    '---',
    `name: ${tmpl.name}`,
    `description: ${tmpl.description}`,
    `allowed-tools: ${allowedTools}`,
    `license: MIT`,
    `compatibility: Requires openspec CLI.`,
    `metadata:`,
    `  author: ${tmpl.metadata?.author || 'openspec'}`,
    `  version: "${tmpl.metadata?.version || '1.0'}"`,
    `  generatedBy: "${version}"`,
    '---',
    '',
    tmpl.instructions.trimEnd(),
  ].join('\n');

  fs.mkdirSync(skillDir, { recursive: true });
  fs.writeFileSync(skillFile, content + '\n', 'utf8');
  console.log(`  ✓ ${skillName} (${tmpl.instructions.length} chars)`);
  updatedCount++;
}

console.log(`\nDone. ${updatedCount} skills updated to @fission-ai/openspec@${version}`);
