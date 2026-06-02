import keytar from "keytar";

const SERVICE_NAME = "codesherlock-cli";
const ACCOUNT_NAME = "default-api-key";

export async function saveApiKeySecurely(apiKey: string): Promise<void> {
    await keytar.setPassword(SERVICE_NAME, ACCOUNT_NAME, apiKey);
}

export async function getSavedApiKeySecurely(): Promise<string | undefined> {
    return (await keytar.getPassword(SERVICE_NAME, ACCOUNT_NAME)) ?? undefined;
}
