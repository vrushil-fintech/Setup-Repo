import { resolve } from "path";
import { GitService } from "../services/gitService.js";
import { BackendApiService } from "../services/backendApiService.js";
import { CommitReviewService } from "../services/commitReviewService.js";
import { runAnalysis } from "../services/analysisEngine.js";
import { logger } from "../services/loggingService.js";
import { CliProgressReporter } from "./CliProgressReporter.js";
import { printResults, printNoIssues } from "./outputFormatter.js";
import { getSavedApiKeySecurely, saveApiKeySecurely } from "./secureApiKeyStore.js";
import { getAppInsightsConnectionString, getBackendApiUrl, getFrontendUrl } from "../config/runtimeConfig.js";


const VALID_FACTORS = ["power_analysis", "owasp", "cwe_mitre", "cwe_kev"] as const;
const VALID_OUTPUT_FORMATS = ["markdown", "json"] as const;

type AnalysisFactor = typeof VALID_FACTORS[number];

type AnalyzeCommandOptions = {
    uncommitted: boolean;
    directory?: string;
    factor: AnalysisFactor;
    apiKey?: string | boolean;
    output: typeof VALID_OUTPUT_FORMATS[number];
};

const API_KEY_PATTERN = /^cs_mcp_[A-Za-z0-9]{20,}$/;

/** Single source of truth for all user-facing web URLs in error messages. */
function getWebBaseUrl(): string {
    return getFrontendUrl();
}

export function buildCommanderErrorMessage(error: { code?: string; message: string }): string {
    const rawMessage = error.message.trim();

    if (error.code === "commander.optionMissingArgument") {
        if (rawMessage.includes("--factor")) {
            return (
                "Error: No analysis factor provided.\n" +
                `Please provide one of the following: ${VALID_FACTORS.join(", ")}.`
            );
        }

        if (rawMessage.includes("--directory")) {
            return (
                "Error: No directory path provided. " +
                "Please pass a repository path with --directory <path>."
            );
        }

        if (rawMessage.includes("--output")) {
            return (
                "Error: No output format provided.\n" +
                `Please provide one of the following: ${VALID_OUTPUT_FORMATS.join(", ")}.`
            );
        }
    }

    if (error.code === "commander.unknownOption") {
        return `${rawMessage}. Run \"codesherlock --help\" to see valid options.`;
    }

    return (
        `${rawMessage}\n` +
        "Run \"codesherlock <command> --help\" for more information."
    );
}

export async function handleAuthCommand(apiKey: string): Promise<void> {
    if (!apiKey) {
        process.stderr.write(
            "Error: API key is required.\n" +
            `Get a valid API key at ${getWebBaseUrl()}/codesherlock-mcp-server/mcp/api/key\n`
        );
        process.exit(1);
        return;
    }

    if (!API_KEY_PATTERN.test(apiKey)) {
        process.stderr.write(
            "Error: Invalid API key format.\n" +
            `Get a valid API key at ${getWebBaseUrl()}/codesherlock-mcp-server/mcp/api/key\n`
        );
        process.exit(1);
        return;
    }

    try {
        await saveApiKeySecurely(apiKey);
        process.stdout.write("API key saved\n");
    } catch {
        process.stderr.write(
            "Error: Unable to securely save API key.\n" +
            "Please try again after enabling OS keychain access on this machine.\n"
        );
        process.exit(1);
    }
}

export async function handleAnalyzeCommand(
    options: AnalyzeCommandOptions
): Promise<void> {
    const directory = resolve(options.directory ?? process.cwd());

    // Commander sets option value to `true` (boolean) when [key] is optional and no value follows.
    // Check that case first, then validate any string value (including empty string).
    if (options.apiKey === true) {
        process.stderr.write(
            "Error: API key is required.\n" +
            `Get a valid API key at ${getWebBaseUrl()}/codesherlock-mcp-server/mcp/api/key\n`
        );
        process.exit(1);
        return;
    }

    if (typeof options.apiKey === "string" && !API_KEY_PATTERN.test(options.apiKey)) {
        process.stderr.write(
            "Error: Invalid API key format.\n" +
            `Get a valid API key at ${getWebBaseUrl()}/codesherlock-mcp-server/mcp/api/key\n`
        );
        process.exit(1);
        return;
    }

    if (!VALID_FACTORS.includes(options.factor as AnalysisFactor)) {
        process.stderr.write(
            `Error: Invalid factor "${options.factor}".\n` +
            `Valid factors are: ${VALID_FACTORS.join(", ")}\n`
        );
        process.exit(1);
        return;
    }

    if (!VALID_OUTPUT_FORMATS.includes(options.output)) {
        process.stderr.write(
            `Error: Invalid output format "${options.output}".\n` +
            `Valid output formats are: ${VALID_OUTPUT_FORMATS.join(", ")}\n`
        );
        process.exit(1);
        return;
    }

    // At this point options.apiKey is either a valid string or undefined
    const flagApiKey = options.apiKey as string | undefined;

    // API key precedence: --api-key flag || secure saved key
    let savedApiKey: string | undefined;
    try {
        savedApiKey = await getSavedApiKeySecurely();
    } catch {
        savedApiKey = undefined;
    }
    const apiKey = flagApiKey || savedApiKey;

    if (!apiKey) {
        const web = getWebBaseUrl();
        process.stderr.write(
            "Error: No API key found.\n" +
            "To get an API key:\n" +
            `1. Visit ${web}/login and sign up or log in.\n` +
            `2. Navigate to the MCP API Keys page: ${web}/codesherlock-mcp-server/mcp/api/key.\n` +
            "3. Generate or copy your API key.\n\n" +
            "Usage instructions:\n" +
            "See the CLI integration guide at https://docs.codesherlock.ai/codesherlock-mcp-server/mcp/setup/guide.\n\n" +
            "If you followed these steps and still face issues, contact support at support@codesherlock.ai."
        );
        process.exit(1);
        return;
    }

    const backendUrl = getBackendApiUrl();

    try {
        const appInsightsConnStr = getAppInsightsConnectionString();
        if (appInsightsConnStr) {
            await logger.initialize(appInsightsConnStr);
        }
    } catch {
        // Non-fatal — proceed without telemetry
    }

    const gitService = new GitService();
    const backendApiService = new BackendApiService(backendUrl, apiKey);
    const commitReviewService = new CommitReviewService(backendApiService);
    const reporter = new CliProgressReporter();

    const analysisStart = Date.now();
    const result = await runAnalysis(
        {
            uncommitted: options.uncommitted,
            directory,
            factor: options.factor,
        },
        { gitService, commitReviewService, backendApiService },
        reporter
    );
    const totalMs = Date.now() - analysisStart;

    reporter.flushTimingSummaryToAzure(totalMs);

    await logger.flush().catch(() => {});

    if (!result.success) {
        process.stderr.write(
            `Error: ${result.errorDetails?.userMessage ?? result.error}\n`
        );
        process.exit(1);
        return;
    }

    if (options.output === "json") {
        process.stdout.write(JSON.stringify(result.results ?? [], null, 2) + "\n");
    } else {
        if (result.results && result.results.length > 0) {
            printResults(result.results);
        } else {
            printNoIssues();
        }
    }

    reporter.printTotalDurationMessage(totalMs);
}
