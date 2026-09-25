namespace CampusAutoLogin;

// Network availability and authentication rejection are different conditions:
// retry outages gradually, but stop submitting rejected credentials.
internal sealed class RetryPolicy
{
    private int failures;
    public bool CredentialsRejected { get; private set; }
    public TimeSpan NextDelay => CredentialsRejected
        ? TimeSpan.FromMinutes(15)
        : TimeSpan.FromSeconds(Math.Min(300, 10 * Math.Pow(2, Math.Min(failures, 5))));

    public void NetworkFailure() => failures = Math.Min(failures + 1, 5);
    public void AuthenticationRejected() => CredentialsRejected = true;
    public void Connected() => failures = 0;
    public void ConfigurationChanged()
    {
        failures = 0;
        CredentialsRejected = false;
    }
}
