import { IProgressReporter } from "../utils/IProgressReporter.js";
import { ProgressStep, formatProgressMessage } from "../utils/progressFormatter.js";
import { TipScheduler, FileTipProvider } from "../utils/progressEmitter.js";
import { logger } from "../services/loggingService.js";
import chalk from "chalk";

/**
 * IProgressReporter implementation for the CLI transport path.
 * Writes progress to stderr so it never pollutes piped stdout (--json mode).
 */
export class CliProgressReporter implements IProgressReporter {
    private readonly scheduler = new TipScheduler();
    private readonly tipsProvider = new FileTipProvider();
    private readonly timings: Array<{ label: string; durationMs: number }> = [];

    private formatCliMessage(step: ProgressStep, data?: any): string {
        if (step === "coding_tip") {
            const tip = data?.tip || "Write clean, maintainable code.";
            return `${chalk.green("Coding tip")}: ${tip}`;
        }

        return formatProgressMessage(step, data);
    }

    async send(step: ProgressStep, _progress: number, _total: number, data?: any): Promise<void> {
        this.scheduler.resetTimestamp();
        const message = this.formatCliMessage(step, data);
        process.stderr.write(`${message}\n`);
    }

    logTiming(label: string, durationMs: number): void {
        this.timings.push({ label, durationMs });
    }

    flushTimingSummaryToAzure(totalMs: number): void {
        const measurements: Record<string, number> = { total_ms: totalMs };
        const properties: Record<string, string> = {};
        for (const { label, durationMs } of this.timings) {
            const key = label
                .toLowerCase()
                .replace(/[^a-z0-9]+/g, "_")
                .replace(/^_+|_+$/g, "");
            if (!key) continue;
            measurements[`${key}_ms`] = durationMs;
            properties[`${key}_ms`] = String(durationMs);
        }

        properties.total_ms = String(totalMs);
        properties.human_readable_total = totalMs < 60_000
            ? `${(totalMs / 1000).toFixed(2)} seconds`
            : `${(totalMs / 60_000).toFixed(2)} minutes`;

        // Searchable trace entry in Azure "traces" table with severity level 1 (information).
        logger.logInfo("CLI Timing Summary", properties);

        logger.logEvent("cli_analysis_timing_summary", undefined, measurements);
        logger.trackMetric("cli_analysis_total_ms", totalMs);
    }

    printTotalDurationMessage(totalMs: number): void {
        const totalSeconds = totalMs / 1000;
        const humanReadable = totalSeconds < 60
            ? `${totalSeconds.toFixed(2)} seconds`
            : `${(totalSeconds / 60).toFixed(2)} minutes`;
        process.stderr.write(`${chalk.green(`CodeSherlock analysis completed in ${humanReadable}.`)}\n`);
    }

    startTipTimer(): void {
        const tips = this.tipsProvider.getTips();
        this.scheduler.start(
            () => tips,
            (tip) => {
                const message = this.formatCliMessage("coding_tip", { tip });
                process.stderr.write(`${message}\n`);
            }
        );
    }

    stopTipTimer(): void {
        this.scheduler.stop();
    }
}
