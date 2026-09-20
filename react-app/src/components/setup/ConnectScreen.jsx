import { useEffect, useState } from "react";
import { Lock } from "lucide-react";
import { useAppState } from "../../state/AppContext";
import * as api from "../../data/client";
import { ContentContainer } from "../layout";
import LoadingState from "../shared/LoadingState";
import { Button } from "@/components/ui/button";

function ZohoMark({ size = 36 }) {
  const height = size;
  const width = Math.round(size * (340 / 130));
  return (
    <svg
      width={width}
      height={height}
      viewBox="0 0 340 130"
      fill="none"
      aria-hidden="true"
    >
      <g strokeWidth="14" strokeLinejoin="round">
        <rect x="10" y="28" width="86" height="86" rx="18" stroke="#E42527" />
        <rect
          x="72"
          y="10"
          width="86"
          height="86"
          rx="18"
          stroke="#1B8F3A"
          transform="rotate(18 115 53)"
        />
        <rect x="166" y="24" width="86" height="86" rx="18" stroke="#1A73C7" />
        <rect x="244" y="28" width="86" height="86" rx="18" stroke="#F0A818" />
      </g>
    </svg>
  );
}

function SalesforceMark({ size = 48 }) {
  return (
    <svg
      width={size}
      height={Math.round(size * 0.68)}
      viewBox="0 0 64 44"
      fill="none"
      aria-hidden="true"
    >
      <path
        fill="#00A1E0"
        d="M22.6 10.8c1.7-1.8 4.1-2.9 6.8-2.9 2.4 0 4.6.9 6.2 2.4 1.5-1 3.3-1.6 5.3-1.6 5 0 9 4 9 9 0 .4 0 .8-.1 1.2 3.2.8 5.6 3.7 5.6 7.2 0 4.1-3.3 7.4-7.4 7.4H16.4C11.2 33.5 7 29.3 7 24.1c0-4.4 3-8.1 7.1-9.1.6-1.7 1.8-3.1 3.4-4.2z"
      />
      <text
        x="32"
        y="26.5"
        textAnchor="middle"
        fill="white"
        fontSize="8"
        fontWeight="700"
        fontFamily="IBM Plex Sans, system-ui, sans-serif"
      >
        salesforce
      </text>
    </svg>
  );
}

function SalesforceCloud({ className, size = 18 }) {
  return (
    <svg
      width={size}
      height={Math.round(size * 0.68)}
      viewBox="0 0 64 44"
      fill="none"
      aria-hidden="true"
      className={className}
    >
      <path
        fill="currentColor"
        d="M22.6 10.8c1.7-1.8 4.1-2.9 6.8-2.9 2.4 0 4.6.9 6.2 2.4 1.5-1 3.3-1.6 5.3-1.6 5 0 9 4 9 9 0 .4 0 .8-.1 1.2 3.2.8 5.6 3.7 5.6 7.2 0 4.1-3.3 7.4-7.4 7.4H16.4C11.2 33.5 7 29.3 7 24.1c0-4.4 3-8.1 7.1-9.1.6-1.7 1.8-3.1 3.4-4.2z"
      />
    </svg>
  );
}

function CrmCard({
  name,
  description,
  logo,
  buttonLabel,
  buttonIcon,
  onConnect,
  notice,
  status,
}) {
  return (
    <div className="flex h-full min-w-0 flex-col items-center rounded-md border border-line bg-[color-mix(in_srgb,var(--brand-soft)_28%,var(--paper))] px-5 py-5 text-center">
      <div className="grid h-12 w-full max-w-[11rem] place-items-center">{logo}</div>
      <h2 className="mt-3 font-heading text-base font-semibold tracking-tight text-ink">
        {name}
      </h2>
      <p className="mt-1.5 max-w-[17rem] text-[13px] leading-snug text-ink-soft">
        {description}
      </p>
      {status && (
        <p className="mt-1.5 max-w-[17rem] text-[12px] leading-snug text-ink-muted">
          {status}
        </p>
      )}
      {notice && (
        <p className="mt-2 max-w-[17rem] text-[13px] text-ink-soft">{notice}</p>
      )}
      <div className="mt-auto w-full max-w-[17rem] pt-4">
        <Button
          type="button"
          size="lg"
          className="h-10 w-full gap-2 bg-brand text-on-brand hover:bg-brand-strong"
          onClick={onConnect}
        >
          {buttonIcon}
          {buttonLabel}
        </Button>
      </div>
    </div>
  );
}

export default function ConnectScreen() {
  const { connection, connectionNotice, salesforceNotice, salesforceConnection } =
    useAppState();
  const [connectingProvider, setConnectingProvider] = useState(null);

  useEffect(() => {
    if (connectingProvider === "zoho") {
      window.location.assign(api.ZOHO_CONSENT_URL);
    }
    if (connectingProvider === "salesforce") {
      window.location.assign(api.SALESFORCE_CONSENT_URL);
    }
  }, [connectingProvider]);

  if (connectingProvider === "zoho") {
    return (
      <ContentContainer className="flex min-h-0 w-full flex-1 flex-col py-8">
        <LoadingState label="Redirecting to Zoho" />
      </ContentContainer>
    );
  }

  if (connectingProvider === "salesforce") {
    return (
      <ContentContainer className="flex min-h-0 w-full flex-1 flex-col py-8">
        <LoadingState label="Redirecting to Salesforce" />
      </ContentContainer>
    );
  }

  const zohoConnected = Boolean(connection) && connection !== "loading";
  const salesforceConnected =
    Boolean(salesforceConnection) && salesforceConnection !== "loading";
  const zohoStatus = zohoConnected
    ? `Connected as ${
        connection.connectedUser?.name ||
        connection.connectedUser?.email ||
        connection.organizationName ||
        connection.organizationId
      }.`
    : null;
  const salesforceStatus = salesforceConnected
    ? `Connected as ${
        salesforceConnection.connectedUser?.name ||
        salesforceConnection.connectedUser?.email ||
        salesforceConnection.organizationName ||
        salesforceConnection.organizationId
      }.`
    : null;

  return (
    <ContentContainer className="flex min-h-full flex-col items-center justify-center py-10 sm:py-14">
      <section
        className="w-full max-w-[44rem] rounded-md border border-line bg-surface px-5 py-7 @min-[640px]:px-8 @min-[640px]:py-8"
        aria-labelledby="connect-crm-title"
      >
        <div className="mx-auto flex max-w-[32rem] flex-col items-center text-center">
          <h1
            id="connect-crm-title"
            className="font-heading text-3xl font-semibold tracking-tight text-ink sm:text-[2rem]"
          >
            Connect to Your CRM
          </h1>
          <p className="mt-2 text-sm leading-relaxed text-ink-soft">
            Choose a CRM to connect. We&apos;ll securely connect to your data and
            help you scan and improve its health.
          </p>
        </div>

        <div className="mt-6 grid grid-cols-1 items-stretch gap-4 @min-[640px]:grid-cols-2">
          <CrmCard
            name="Zoho CRM"
            description="Connect your Zoho CRM account to start scanning your data."
            logo={<ZohoMark size={40} />}
            buttonLabel="Connect Zoho CRM"
            buttonIcon={<ZohoMark size={16} />}
            onConnect={() => setConnectingProvider("zoho")}
            notice={connectionNotice}
            status={zohoStatus}
          />
          <CrmCard
            name="Salesforce CRM"
            description="Connect your Salesforce account to start scanning your data."
            logo={<SalesforceMark size={48} />}
            buttonLabel="Connect Salesforce CRM"
            buttonIcon={<SalesforceCloud size={18} />}
            onConnect={() => setConnectingProvider("salesforce")}
            notice={salesforceNotice}
            status={salesforceStatus}
          />
        </div>

        <p className="mt-6 flex items-center justify-center gap-2 border-t border-line pt-5 text-[12px] text-ink-muted">
          <Lock className="size-3.5 shrink-0" aria-hidden="true" />
          Your data is secure. We use industry-standard OAuth authentication.
        </p>
      </section>
    </ContentContainer>
  );
}
