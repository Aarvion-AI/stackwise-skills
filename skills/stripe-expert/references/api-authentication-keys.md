# API Authentication and Key Management

## Stripe API Keys

Stripe uses two types of API keys: publishable and secret.

| Key Type | Visibility | Used For | Exposure Risk |
|---|---|---|---|
| **Publishable** (`pk_live_...`, `pk_test_...`) | Client-side (safe) | Creating payment methods, Stripe.js, initializing elements | Low - intended to be public |
| **Secret** (`sk_live_...`, `sk_test_...`) | Server-side only | Creating payment intents, creating charges, retrieving resources | **Critical** - must be protected |

## Environment Setup

### .env File (Server-Side Only)

```bash
# Test environment
STRIPE_SECRET_KEY=sk_test_YOUR_TEST_SECRET_KEY_HERE
STRIPE_PUBLIC_KEY=pk_test_YOUR_TEST_PUBLIC_KEY_HERE
STRIPE_WEBHOOK_SECRET=whsec_test_your_webhook_secret

# Live environment (use different variables or entire .env)
STRIPE_LIVE_SECRET_KEY=sk_live_YOUR_LIVE_SECRET_KEY_HERE
STRIPE_LIVE_PUBLIC_KEY=pk_live_YOUR_LIVE_PUBLIC_KEY_HERE
STRIPE_LIVE_WEBHOOK_SECRET=whsec_live_your_webhook_secret
```

### Environment-Based Key Selection

```javascript
// Node.js
const apiKey = process.env.NODE_ENV === 'production'
  ? process.env.STRIPE_LIVE_SECRET_KEY
  : process.env.STRIPE_SECRET_KEY;

const stripe = require('stripe')(apiKey);
```

```python
# Python
import os
import stripe

api_key = os.getenv('STRIPE_LIVE_SECRET_KEY' if os.getenv('ENVIRONMENT') == 'production' else 'STRIPE_SECRET_KEY')
stripe.api_key = api_key
```

### React/Frontend (Use Public Key Only)

```jsx
import { loadStripe } from '@stripe/js';

// ✅ CORRECT: Use public key in frontend
const stripe = loadStripe(process.env.REACT_APP_STRIPE_PUBLIC_KEY);

// ❌ WRONG: Never expose secret key to frontend
const stripe = loadStripe(process.env.STRIPE_SECRET_KEY); // BREACH
```

## Key Rotation Strategy

Rotate keys regularly to limit exposure window in case of compromise.

### 1. Generate New Restricted Key

In Stripe Dashboard, create a restricted API key with minimal permissions:

```
Permissions:
- Read: Customers, Charges, Invoices, Subscriptions
- Write: Charges (create, capture, refund), Customers (create, update)
```

### 2. Update in Production

```javascript
// Gradually roll out new key to prevent simultaneous key failures
// 1. Deploy with both old and new keys
const apiKeys = [
  process.env.STRIPE_SECRET_KEY_NEW,
  process.env.STRIPE_SECRET_KEY_OLD,
];

// 2. Try new key first, fallback to old
async function createPaymentIntent(amount) {
  for (const key of apiKeys) {
    try {
      const stripe = require('stripe')(key);
      return await stripe.paymentIntents.create({ amount, currency: 'usd' });
    } catch (error) {
      console.warn(`Key failed: ${key.slice(-4)}, trying next...`);
    }
  }
  throw new Error('All Stripe API keys failed');
}
```

### 3. Disable Old Key

After confirming the new key works, disable the old key in Stripe Dashboard.

## Restricted API Keys

Create restricted keys with minimal permissions for different services:

### Payment Processing Key
```
Permissions:
- Read: Charges, PaymentIntents
- Write: PaymentIntents, Charges
- Scope: Payment processing only
```

### Subscription Management Key
```
Permissions:
- Read: Subscriptions, Customers, Invoices
- Write: Subscriptions, Customers, Invoices
- Scope: Subscription/billing only
```

### Webhook Listener Key
```
Permissions:
- Read: All resources (needed to fetch full objects from webhooks)
- Write: None
- Scope: Event retrieval only
```

## Secret Management in Different Environments

### Local Development

Use `.env` file (never commit):

```bash
# .env.local (gitignored)
STRIPE_SECRET_KEY=sk_test_...
STRIPE_PUBLIC_KEY=pk_test_...
```

### Staging / Production

Use environment variables managed by your platform:

**AWS Lambda / Secrets Manager:**
```bash
aws secretsmanager put-secret \
  --name stripe/production/secret-key \
  --secret-string sk_live_...
```

```javascript
const AWS = require('aws-sdk');
const client = new AWS.SecretsManager();

async function getStripeKey() {
  const secret = await client.getSecretValue({ SecretId: 'stripe/production/secret-key' }).promise();
  return JSON.parse(secret.SecretString).apiKey;
}
```

**Vercel / Environment Variables:**
```bash
vercel env add STRIPE_SECRET_KEY
```

**Docker / Kubernetes:**
```yaml
# kubernetes secret
apiVersion: v1
kind: Secret
metadata:
  name: stripe-keys
type: Opaque
data:
  api-key: c2tfbGl2ZV8uLi4=  # base64 encoded sk_live_...
```

```dockerfile
# Dockerfile - never hardcode keys
FROM node:18
ENV STRIPE_SECRET_KEY=$STRIPE_SECRET_KEY
```

## Security Best Practices

### 1. Never Expose Secret Key

```javascript
// ❌ WRONG: Logging or exposing secret
console.log('Stripe key:', process.env.STRIPE_SECRET_KEY);
res.json({ secretKey: process.env.STRIPE_SECRET_KEY }); // Breach!

// ✅ CORRECT: Use key internally, never expose
const stripe = require('stripe')(process.env.STRIPE_SECRET_KEY);
// Key stays server-side only
```

### 2. Don't Store Keys in Code or .env in Git

```bash
# .gitignore
.env
.env.local
.env.*.local
config/secrets.js
```

### 3. Use Restricted Keys for Different Services

Instead of one universal secret key, create restricted keys per service:

```javascript
// payments-service.js
const stripePayments = require('stripe')(
  process.env.STRIPE_PAYMENTS_KEY // write-only, payments scope
);

// subscriptions-service.js
const stripeSubscriptions = require('stripe')(
  process.env.STRIPE_SUBSCRIPTIONS_KEY // subscriptions scope
);
```

### 4. Monitor Key Usage

In Stripe Dashboard, Developers > Events > Filter by API key:

- Watch for unusual activity (many failed requests, high volume, unexpected resources)
- Set up alerts in your monitoring tool (Datadog, New Relic, etc.)
- Review API request logs monthly

### 5. Audit Trail and Rotation Schedule

Maintain a record of key rotations:

```
Key Rotation Log:
- 2024-01-15: Generated sk_live_xyz, deployed to production
- 2024-02-15: Verified key stable, generated sk_live_abc
- 2024-02-20: Switched to sk_live_abc, disabled sk_live_xyz
```

Rotate keys at least quarterly or immediately if compromised.

## Testing Key Configurations

```javascript
// Verify key is correctly loaded
function validateStripeConfiguration() {
  const secretKey = process.env.STRIPE_SECRET_KEY;
  const publicKey = process.env.STRIPE_PUBLIC_KEY;

  if (!secretKey) throw new Error('STRIPE_SECRET_KEY not set');
  if (!publicKey) throw new Error('STRIPE_PUBLIC_KEY not set');

  // Verify key format
  if (!secretKey.startsWith('sk_test_') && !secretKey.startsWith('sk_live_')) {
    throw new Error('STRIPE_SECRET_KEY has invalid format');
  }

  if (!publicKey.startsWith('pk_test_') && !publicKey.startsWith('pk_live_')) {
    throw new Error('STRIPE_PUBLIC_KEY has invalid format');
  }

  console.log(`✓ Using ${secretKey.startsWith('sk_test') ? 'test' : 'live'} keys`);
}

// Run on startup
validateStripeConfiguration();
```

## Deployment Checklist

Before deploying:

- [ ] Secret key is in environment variables, not in code
- [ ] Public key is correctly configured for the environment (test vs live)
- [ ] Webhook secret is registered and matches the endpoint
- [ ] No console.log statements printing sensitive data
- [ ] API key permissions are restricted (not using full-access universal key)
- [ ] Different keys for test and production environments
- [ ] Key rotation schedule documented
- [ ] Monitoring/alerts set up for suspicious API activity
