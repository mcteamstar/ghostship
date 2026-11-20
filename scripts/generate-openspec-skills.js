#!/usr/bin/env node
/**
 * generate-openspec-skills.js
 *
 * Generate Academy's six core OpenSpec workflow skills from the installed
 * @fission-ai/openspec package's shared-skill templates. The CLI and generated
 * skills are a coupled versioned asset. Ghostship uses skill delivery, so the
 * examples are adapted away from OpenSpec command-file invocations.
 *
 * Usage:
 *   npm install -g @fission-ai/openspec@<version>
 *   node scripts/generate-openspec-skills.js
 */

const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');
const { pathToFileURL } = require('url');

const CORE_SKILLS = [
  ['explore', 'openspec-explore'],
  ['propose', 'openspec-propose'],
  ['update', 'openspec-update-change'],
  ['apply', 'openspec-apply-change'],
  ['sync', 'openspec-sync-specs'],
  ['archive', 'openspec-archive-change'],
];

const GHOSTSHIP_EXAMPLE_REPLACEMENTS = [
  ['User: /opsx:explore add-auth-system',
    'User: Use the openspec-explore skill to explore add-auth-system'],
  ['`/opsx:apply add-auth`',
    'the `openspec-apply-change` skill for `add-auth`'],
  ['`/opsx:apply <other>`',
    'the `openspec-apply-change` skill for `<other>`'],
  ['`/opsx:update <other>`',
    'the `openspec-update-change` skill for `<other>`'],
  ['`/opsx:sync <other>`',
    'the `openspec-sync-specs` skill for `<other>`'],
  ['`/opsx:archive <other>`',
    'the `openspec-archive-change` skill for `<other>`'],
];

function adaptInstructions(instructions) {
  let result = instructions;
  for (const [source, replacement] of GHOSTSHIP_EXAMPLE_REPLACEMENTS) {
    result = result.replaceAll(source, replacement);
  }
  if (/\/opsx:|\[\[opsx:/i.test(result)) {
    throw new Error('Unadapted OpenSpec command-file reference remains in a core skill template');
  }
  return result;
}

async function main() {
  const npmRoot = execSync('npm root -g', { encoding: 'utf8' }).trim();
  const openspecRoot = path.join(npmRoot, '@fission-ai', 'openspec');
  const pkgJson = JSON.parse(fs.readFileSync(path.join(openspecRoot, 'package.json'), 'utf8'));
  const version = pkgJson.version;
  const generatorPath = path.join(openspecRoot, 'dist', 'core', 'shared', 'skill-generation.js');
  const { getSkillTemplates, generateSkillContent } = await import(pathToFileURL(generatorPath).href);
  const workflows = CORE_SKILLS.map(([workflowId]) => workflowId);
  const templates = getSkillTemplates(workflows);
  const templatesByWorkflow = new Map(templates.map((entry) => [entry.workflowId, entry]));

  console.log(`Generating Academy skills from @fission-ai/openspec@${version}`);

  const repoRoot = path.resolve(__dirname, '..');
  const skillsBase = path.join(repoRoot, 'academy', 'skills');
  let updatedCount = 0;

  for (const [workflowId, skillName] of CORE_SKILLS) {
    const entry = templatesByWorkflow.get(workflowId);
    if (!entry || entry.dirName !== skillName) {
      throw new Error(`Missing or unexpected OpenSpec skill template for ${workflowId}: expected ${skillName}`);
    }

    const skillDir = path.join(skillsBase, skillName);
    const skillFile = path.join(skillDir, 'SKILL.md');
    const content = generateSkillContent(entry.template, version, adaptInstructions);

    fs.mkdirSync(skillDir, { recursive: true });
    fs.writeFileSync(skillFile, content, 'utf8');
    console.log(`  ✓ ${skillName} (${entry.template.instructions.length} chars)`);
    updatedCount++;
  }

  if (updatedCount !== CORE_SKILLS.length) {
    throw new Error(`Expected ${CORE_SKILLS.length} core skills, generated ${updatedCount}`);
  }
  console.log(`\nDone. ${updatedCount} skills updated to @fission-ai/openspec@${version}`);
}

main().catch((error) => {
  console.error(error.message || error);
  process.exitCode = 1;
});
