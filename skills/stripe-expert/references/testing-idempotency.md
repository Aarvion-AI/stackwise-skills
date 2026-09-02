# Testing and Idempotency

## Test Mode vs. Live Mode

Always develop and test in **test mode** before going live.

| Aspect | Test Mode | Live Mode |
|---|---|---|
| API Keys | `pk_test_...`, `sk_test_...` | `pk_live_...`, `sk_live_...` |
| Charges | Test charges only, no real money | Real transactions to real cards |
| Refunds | Instant, no hold period | Subject to processing times |
| Webhooks | Simulated via dashboard | Real Stripe events |
| Data Isolation | Separate from live | Production data |

## Test Card Numbers

Use these test card numbers in test mode (CVV: any 3 digits, expiry: any future date):

```
4242 4242 4242 4242  - Success
4000 0000 0000 0002  - Decline: generic decline
4000 0000 0000 9995  - Decline: insufficient funds
4000 0000 0000 9987  - Decline: lost card
4000 0000 0000 9979  - Decline: stolen card
4000 0000 0000 0069  - Decline: expired card
4000 0000 0000 0127  - Decline: incorrect CVC
5200 0000 0000 0007  - Success with Mastercard
3782 822463 10005    - Success with Amex
6011 1111 1111 1117  - Success with Discover

3D Secure / Authentication Required:
4000 0025 0000 3155  - 3D Secure required (authentication)
4000 0027 6000 3184  - 3D Secure required (authentication failed)
```

## Writing Tests

### Unit Test: Payment Creation

```javascript
// payment.test.js
const stripe = require('stripe')(process.env.STRIPE_SECRET_KEY);
const { createPaymentIntent } = require('./payment');

describe('Payment Processing', () => {
  it('should create a payment intent with idempotency key', async () => {
    const orderId = 'order-123';
    const amount = 9900;
    const idempotencyKey = `order-${orderId}-${Date.now()}`;

    const paymentIntent = await createPaymentIntent(orderId, amount, {
      idempotencyKey,
    });

    expect(paymentIntent.id).toMatch(/^pi_/);
    expect(paymentIntent.amount).toBe(amount);
    expect(paymentIntent.status).toBe('succeeded');
    expect(paymentIntent.metadata.orderId).toBe(orderId);
  });

  it('should return the same payment intent with duplicate idempotency key', async () => {
    const orderId = 'order-456';
    const idempotencyKey = `order-${orderId}-test`;

    const intent1 = await createPaymentIntent(orderId, 5000, {
      idempotencyKey,
    });
    const intent2 = await createPaymentIntent(orderId, 5000, {
      idempotencyKey,
    });

    expect(intent1.id).toBe(intent2.id);
  });

  it('should handle card decline errors', async () => {
    const testCardToken = await stripe.tokens.create({
      card: {
        number: '4000000000000002', // Decline test card
        exp_month: 12,
        exp_year: 2025,
        cvc: '123',
      },
    });

    expect(async () => {
      await stripe.paymentIntents.create({
        amount: 5000,
        currency: 'usd',
        payment_method_types: ['card'],
        source: testCardToken.id,
      });
    }).rejects.toThrow();
  });
});
```

### Integration Test: End-to-End Payment

```javascript
// payment.integration.test.js
describe('Payment Flow Integration', () => {
  it('should complete full checkout flow', async () => {
    // 1. Create customer
    const customer = await stripe.customers.create({
      email: 'test@example.com',
      metadata: { userId: 'user-123' },
    });

    expect(customer.id).toMatch(/^cus_/);

    // 2. Create payment method
    const paymentMethod = await stripe.paymentMethods.create({
      type: 'card',
      card: {
        number: '4242424242424242',
        exp_month: 12,
        exp_year: 2025,
        cvc: '123',
      },
    });

    expect(paymentMethod.id).toMatch(/^pm_/);

    // 3. Create payment intent
    const paymentIntent = await stripe.paymentIntents.create({
      amount: 2000,
      currency: 'usd',
      customer: customer.id,
      payment_method: paymentMethod.id,
      confirm: true,
    });

    // 4. Verify payment succeeded
    expect(paymentIntent.status).toBe('succeeded');

    // 5. Verify charge was created
    const charges = await stripe.charges.list({ limit: 1 });
    expect(charges.data[0].customer).toBe(customer.id);
  });

  it('should verify webhook delivery for payment event', async () => {
    // 1. Set up webhook listener (mock)
    const webhookReceived = jest.fn();

    // 2. Create payment
    const paymentIntent = await stripe.paymentIntents.create({
      amount: 2000,
      currency: 'usd',
      confirm: true,
      payment_method_types: ['card'],
      source: 'tok_visa',
    });

    // 3. Simulate webhook delivery (in test mode, use Stripe CLI)
    const event = {
      type: 'payment_intent.succeeded',
      data: { object: paymentIntent },
    };

    // 4. Verify handler was called
    webhookReceived(event);
    expect(webhookReceived).toHaveBeenCalledWith(expect.objectContaining({
      type: 'payment_intent.succeeded',
    }));
  });
});
```

## Idempotency: Preventing Duplicate Charges

Idempotency ensures that retried requests don't create duplicate charges.

### How Idempotency Works

```
Request 1: POST /paymentIntents with idempotencyKey="order-123"
  → Creates PaymentIntent, returns it
  → Stripe stores the mapping: idempotencyKey -> pi_xyz

Request 2 (retry): POST /paymentIntents with same idempotencyKey="order-123"
  → Stripe sees the key is known, returns cached pi_xyz
  → No duplicate charge created
```

### Using Idempotency Keys

```javascript
const stripe = require('stripe')(process.env.STRIPE_SECRET_KEY);

async function createPaymentWithIdempotency(amount, orderId) {
  const idempotencyKey = `order-${orderId}`;

  // Request 1: Create intent
  const intent1 = await stripe.paymentIntents.create(
    { amount, currency: 'usd' },
    { idempotencyKey }
  );

  // If network fails and request is retried...
  // Request 2 (retry): Same intent is returned
  const intent2 = await stripe.paymentIntents.create(
    { amount, currency: 'usd' },
    { idempotencyKey }
  );

  // intent1.id === intent2.id ✓
  return intent1;
}
```

### Idempotency Key Format

Generate unique keys per logical operation:

```javascript
// ✅ GOOD: Unique per order attempt
const idempotencyKey = `order-${orderId}-${Date.now()}`;

// ✅ GOOD: UUID
const { v4: uuid } = require('uuid');
const idempotencyKey = uuid();

// ❌ BAD: Same key every time (won't work for retries)
const idempotencyKey = 'my-payment'; // Static

// ❌ BAD: Repeats on refresh
const idempotencyKey = orderId; // User refreshes page, same key, returns old intent
```

### Idempotency for Subscriptions

```javascript
async function createSubscriptionWithIdempotency(customerId, priceId, orderId) {
  const idempotencyKey = `subscription-${orderId}`;

  const subscription = await stripe.subscriptions.create(
    {
      customer: customerId,
      items: [{ price: priceId }],
      payment_behavior: 'default_incomplete',
    },
    { idempotencyKey }
  );

  return subscription;
}
```

## Testing Webhooks Locally

### Option 1: Stripe CLI (Recommended)

```bash
# Install Stripe CLI (https://stripe.com/docs/stripe-cli)

# Forward Stripe events to your local endpoint
stripe listen --api-key sk_test_... --forward-to localhost:3000/webhooks/stripe

# In another terminal, trigger test events
stripe trigger payment_intent.succeeded
stripe trigger charge.refunded
stripe trigger customer.subscription.created
```

### Option 2: Stripe Dashboard Test Events

1. Go to Stripe Dashboard > Developers > Webhooks
2. Find your endpoint
3. Click "Send test event"
4. Choose event type and data
5. Watch your logs to verify receipt

### Option 3: Manual Event Simulation

```javascript
// test-webhook.js - Send test webhook to your endpoint
const crypto = require('crypto');

function generateWebhookSignature(payload, secret) {
  const timestamp = Math.floor(Date.now() / 1000);
  const signedContent = `${timestamp}.${payload}`;
  const signature = crypto
    .createHmac('sha256', secret)
    .update(signedContent)
    .digest('hex');
  return `t=${timestamp},v1=${signature}`;
}

async function sendTestWebhook(webhookUrl, event, webhookSecret) {
  const payload = JSON.stringify(event);
  const signature = generateWebhookSignature(payload, webhookSecret);

  const response = await fetch(webhookUrl, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'stripe-signature': signature,
    },
    body: payload,
  });

  return response;
}

// Usage
const testEvent = {
  id: 'evt_test_123',
  type: 'payment_intent.succeeded',
  created: Math.floor(Date.now() / 1000),
  data: {
    object: {
      id: 'pi_test_123',
      status: 'succeeded',
      amount: 2000,
      currency: 'usd',
      metadata: { orderId: 'order-123' },
    },
  },
};

sendTestWebhook(
  'http://localhost:3000/webhooks/stripe',
  testEvent,
  process.env.STRIPE_WEBHOOK_SECRET
);
```

## Verifying Payment Tests

After running a payment test in test mode, verify it in Stripe Dashboard:

1. **Go to Developers > Events**
   - Look for `payment_intent.created`, `payment_intent.succeeded`
   - Verify metadata matches your order

2. **Check Charges**
   - Developers > Charges
   - Verify amount, customer, and status

3. **Check Webhooks**
   - Developers > Webhooks > Your Endpoint
   - Click "View events" to see delivery history
   - Look for successful deliveries (HTTP 200)

## Mocking Stripe in Tests

For unit tests that don't call real Stripe:

```javascript
// payment.mock.test.js
const stripe = require('stripe');

jest.mock('stripe', () => {
  return jest.fn(() => ({
    paymentIntents: {
      create: jest.fn().mockResolvedValue({
        id: 'pi_mock_123',
        status: 'succeeded',
        amount: 2000,
        metadata: { orderId: 'order-123' },
      }),
      retrieve: jest.fn().mockResolvedValue({
        id: 'pi_mock_123',
        status: 'succeeded',
      }),
    },
    customers: {
      create: jest.fn().mockResolvedValue({
        id: 'cus_mock_123',
        email: 'test@example.com',
      }),
    },
  }));
});

describe('Payment Service (Mocked)', () => {
  it('should handle payment intent creation', async () => {
    const stripeInstance = stripe();
    const result = await stripeInstance.paymentIntents.create({
      amount: 2000,
      currency: 'usd',
    });

    expect(result.id).toBe('pi_mock_123');
    expect(result.status).toBe('succeeded');
  });
});
```

## Checklist Before Going Live

- [ ] Switch to live API keys (`sk_live_...`, `pk_live_...`)
- [ ] Test payment flow end-to-end on staging with real webhooks
- [ ] Verify webhook endpoint is HTTPS only
- [ ] Verify webhook secret is in environment variables (not code)
- [ ] Test at least one refund flow
- [ ] Test subscription creation and cancellation
- [ ] Verify error messages shown to customers are user-friendly
- [ ] Set up monitoring/alerts for failed payments
- [ ] Set up error tracking (Sentry, DataDog, etc.)
- [ ] Document payment flow and disaster recovery procedures
- [ ] Run security audit of payment handling code
- [ ] Review PCI compliance requirements (use Stripe SDKs, avoid storing raw card data)
