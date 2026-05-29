#!/usr/bin/env node

import { Command, CommanderError } from "commander";
import packageJson from "../../packages/cli/package.json";
import { printWelcomeBanner } from "./welcomeBanner.js";

export async function run(argv: string[]): Promise<void> {
    const program = new Command();

    program
        .name("codesherlock")
        .description("AI-powered code analysis for security, quality, and compliance")
        .version(packageJson.version)
        .exitOverride()
        .configureOutput({
            // Suppress Commander default error output so we can provide clearer messages.
            writeErr: () => undefined,
        });

    // -------------------------------------------------------------------------
    // auth command — saves API key 
    // -------------------------------------------------------------------------
    program
        .command("auth [api-key]")
        .description("Authenticate with your CodeSherlock API key")
        .action(async (apiKey: string | undefined) => {
            const { handleAuthCommand } = await import("./cliCommandHandlers.js");
            await handleAuthCommand(apiKey ?? "");
        });

    // -------------------------------------------------------------------------
    // analyze command
    // -------------------------------------------------------------------------
    program
        .command("analyze")
        .description("Analyze code changes in a git repository")
        .option("--uncommitted", "Analyze staged/unstaged changes instead of last commit", false)
        .option("--directory <path>", "Path to the git repository (default: current directory)")
        .option("--factor <name>", "Analysis focus: power_analysis, owasp, cwe_mitre, cwe_kev", "power_analysis")
        .option("--api-key [key]", "API key for this run")
        .option("--output <format>", "Output format: markdown or json", "markdown")
        .action(async (options) => {
            const { handleAnalyzeCommand } = await import("./cliCommandHandlers.js");
            await handleAnalyzeCommand(options);
        });

    // Show branded welcome output for bare `codesherlock`.
    if (argv.length <= 2) {
        printWelcomeBanner();
        program.outputHelp();
        return;
    }

    try {
        await program.parseAsync(argv);
    } catch (error) {
        if (error instanceof CommanderError) {
            // Keep Commander default behavior for --help/--version success exits.
            if (error.exitCode === 0) {
                throw error;
            }

            const { buildCommanderErrorMessage } = await import("./cliCommandHandlers.js");
            process.stderr.write(`${buildCommanderErrorMessage(error)}\n`);
            process.exit(error.exitCode ?? 1);
            return;
        }

        throw error;
    }
}

// Only auto-run when invoked directly as CLI, not when imported in tests)
if (process.env.NODE_ENV !== "test") {
    run(process.argv).catch((error) => {
        if (error instanceof CommanderError) {
            process.exit(error.exitCode ?? 0);
        }
        process.stderr.write(
            `Fatal error: ${error instanceof Error ? error.message : String(error)}\n`
        );
        process.exit(1);
    });
}
