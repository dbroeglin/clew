import assert from "node:assert/strict";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import { validateVaultBinding } from "../binding.mjs";
import { CaptureError } from "../errors.mjs";
import { makeVault } from "./fixtures.mjs";

test("vault binding requires an existing absolute directory outside the repository", async () => {
    const repository = await makeVault();
    const externalVault = await makeVault();
    assert.equal(await validateVaultBinding(externalVault, repository), externalVault);

    await assert.rejects(
        () => validateVaultBinding("relative-vault", repository),
        (error) => error instanceof CaptureError && error.code === "invalid_vault",
    );
    await assert.rejects(
        () => validateVaultBinding(path.join(repository, "missing"), repository),
        (error) => error instanceof CaptureError && error.code === "invalid_vault",
    );
    await mkdir(path.join(repository, "nested"), { recursive: true });
    await assert.rejects(
        () => validateVaultBinding(path.join(repository, "nested"), repository),
        (error) => error instanceof CaptureError && error.code === "invalid_vault",
    );
    await writeFile(path.join(repository, "not-a-directory"), "x", "utf8");
    await assert.rejects(
        () => validateVaultBinding(path.join(repository, "not-a-directory"), externalVault),
        (error) => error instanceof CaptureError && error.code === "invalid_vault",
    );
});
