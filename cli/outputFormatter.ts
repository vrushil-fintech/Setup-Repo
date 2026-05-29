import chalk from "chalk";
import { IssueItem, CharacteristicAnalysis } from "../utils/analysisFormatter.js";
import { AnalysisResultItem } from "../services/commitReviewService.js";

function severityColor(severity: string): chalk.Chalk {
    const s = (severity ?? "").toLowerCase();
    switch (s) {
        case "critical": return chalk.redBright.bold;
        case "high":     return chalk.red;
        case "medium":   return chalk.yellow;
        case "low":      return chalk.cyan;
        default:         return chalk.white;
    }
}

function severityLabel(severity?: string): string {
    const safe = String(severity ?? "UNKNOWN").toUpperCase();
    return severityColor(safe)(safe.padEnd(8));
}

const DIVIDER = chalk.gray("─".repeat(60));
const THICK_DIVIDER = chalk.gray("═".repeat(60));

function codeBlock(snippet?: string): string {
    const text = snippet == null ? "" : String(snippet);
    return text
        .split("\n")
        .map((l) => chalk.gray("  │ ") + chalk.green(l))
        .join("\n");
}

function renderIssue(issue: IssueItem, language: string): string {
    const lines: string[] = [];

    lines.push(`  ${severityLabel(issue.severity)} ${issue.issue}`);

    if (issue.start_line && issue.end_line) {
        lines.push(`  ${chalk.gray("Lines:")} ${issue.start_line}–${issue.end_line}`);
    }

    if (issue.issue_code_snippet) {
        lines.push(chalk.gray("  Problem:"));
        lines.push(codeBlock(issue.issue_code_snippet));
    }

    lines.push(`  ${chalk.gray("Solution:")} ${issue.solution}`);

    if (issue.solution_code_snippet) {
        lines.push(chalk.gray("  Fix:"));
        lines.push(codeBlock(issue.solution_code_snippet));
    }

    return lines.join("\n");
}

export function printResults(results: AnalysisResultItem[]): void {
    process.stdout.write(THICK_DIVIDER + "\n");
    process.stdout.write(chalk.bold.white("  CodeSherlock Analysis Results") + "\n");
    process.stdout.write(THICK_DIVIDER + "\n\n");

    let totalIssues = 0;

    for (const result of results) {
        try {
            process.stdout.write(chalk.bold.blue(`File: ${result.file_name}`) + "\n");
            process.stdout.write(DIVIDER + "\n");

            const analysis: (CharacteristicAnalysis | null)[] = Array.isArray(result.analysis)
                ? result.analysis
                : [];

            for (const characteristic of analysis) {
                if (!characteristic) continue;

                process.stdout.write(
                    chalk.bold.white(`\n  ${characteristic.characteristic}`) + "\n"
                );
                if (characteristic.description_of_characteristic) {
                    process.stdout.write(
                        chalk.gray(`  ${characteristic.description_of_characteristic}`) + "\n"
                    );
                }

                const issueItems = characteristic.issue_items ?? [];
                for (const issue of issueItems) {
                    process.stdout.write("\n" + renderIssue(issue, result.language ?? "") + "\n");
                    totalIssues++;
                }
            }

            process.stdout.write("\n");
        } catch (err) {
            process.stderr.write(
                chalk.red(`Error rendering analysis for file ${result.file_name}: ${String(err)}\n`)
            );
        }
    }

    process.stdout.write(THICK_DIVIDER + "\n");
    const summary =
        totalIssues === 1
            ? "  1 issue found."
            : `  ${totalIssues} issues found.`;
    process.stdout.write(chalk.bold(summary) + "\n");
    process.stdout.write(THICK_DIVIDER + "\n");
}

export function printNoIssues(): void {
    process.stdout.write(THICK_DIVIDER + "\n");
    process.stdout.write(chalk.bold.white("  CodeSherlock Analysis Results") + "\n");
    process.stdout.write(THICK_DIVIDER + "\n\n");
    process.stdout.write(chalk.green("  No issues found.") + "\n\n");
    process.stdout.write(THICK_DIVIDER + "\n");
}
