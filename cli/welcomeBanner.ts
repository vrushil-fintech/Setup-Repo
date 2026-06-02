import packageJson from "../../packages/cli/package.json";

export function printWelcomeBanner(): void {
    const banner = [
        "",
        "   ____          _      ____  _               _            _   ",
        "  / ___|___   __| | ___/ ___|| |__   ___ _ __| | ___   ___| | __",
        " | |   / _ \\ / _` |/ _ \\___ \\| '_ \\ / _ \\ '__| |/ _ \\ / __| |/ /",
        " | |__| (_) | (_| |  __/___) | | | |  __/ |  | | (_) | (__|   < ",
        "  \\____\\___/ \\__,_|\\___|____/|_| |_|\\___|_|  |_|\\___/ \\___|_|\\_\\",
        "",
        ` CodeSherlock CLI v${packageJson.version}`,
        " AI-powered code analysis for security, quality, and compliance",
        "",
    ].join("\n");

    process.stdout.write(`${banner}\n`);
}
