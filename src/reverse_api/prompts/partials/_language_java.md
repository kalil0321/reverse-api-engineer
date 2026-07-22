**Generate a Java program** that replicates the API calls found in the traffic. The following are guidelines — use your judgment on what's appropriate for the specific API:

- Use `java.net.http.HttpClient` (built into the JDK since 11) for requests — no HTTP library dependency needed
- Use Gson for JSON parsing/serialization — the one dependency this needs, since the JDK has no built-in JSON support
- Create a minimal Maven project (`pom.xml`) with the Gson dependency and the `exec-maven-plugin`, so the client runs with a single command and no extra flags. A conventional Maven layout only compiles `src/main/java`, but `{client_filename}` is saved at the project root (see below) — override the build's `<sourceDirectory>` to `.` (project root) in the POM so `mvn compile` actually finds and compiles it
- Configure `exec-maven-plugin` for the `exec:exec` goal with exactly this configuration — do not use the `exec:java` goal or `<mainClass>`: `exec:java` invokes `main` reflectively in-process, which fails on the package-private `ApiClient` class described below ("symbolic reference class is not accessible"), while `exec:exec` spawns a real `java` process, and its `<classpath/>` element expands to the full dependency classpath with the correct platform-specific separator (`:` on macOS/Linux, `;` on Windows):

  ```xml
  <plugin>
      <groupId>org.codehaus.mojo</groupId>
      <artifactId>exec-maven-plugin</artifactId>
      <version>3.1.0</version>
      <configuration>
          <executable>java</executable>
          <arguments>
              <argument>-classpath</argument>
              <classpath/>
              <argument>ApiClient</argument>
          </arguments>
      </configuration>
  </plugin>
  ```
- Create a separate method for each distinct API endpoint, with a small class for its response shape
- Reuse one `HttpClient` instance across requests rather than creating a new one per call
- Include a `main` method with example usage
- The output file is named `{client_filename}` (lowercase with underscores), so name the top-level class holding `main` exactly `ApiClient`, declared package-private, *without* the `public` modifier — a `public` class's filename must exactly match its class name, and this generator's file naming convention doesn't follow Java's usual PascalCase file naming. A package-private top-level class compiles and runs identically; it just isn't visible from other packages, which this single-file client has no need for.

**Authentication & credentials:**
- Hardcode all cookies, tokens, session IDs, and auth headers found in the traffic directly in the program
- The user should be able to run the program immediately after `mvn compile` — no env vars, no additional config files, no manual setup beyond what's generated
- If the API uses cookies, build the `HttpClient` with a `CookieHandler`/`CookieManager` so cookies persist across requests
- If the API uses Bearer tokens or API keys, hardcode them in the request headers
- Handle auth refresh so the program doesn't go stale: if you see a token refresh endpoint, OAuth refresh flow, or login endpoint in the traffic, implement automatic re-authentication when a request returns 401/403. If cookies have expiry, re-fetch them before they expire

**Testing:**
- Run: `{run_command}`
- You have up to 5 attempts to fix issues

Save the program to: `{scripts_dir}/{client_filename}`
Save documentation to: `{scripts_dir}/README.md`
Save the Maven project file to: `{scripts_dir}/pom.xml`
