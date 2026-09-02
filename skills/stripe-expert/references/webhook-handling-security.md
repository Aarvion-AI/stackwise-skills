# Webhook Handling and Security

## What Are Webhooks?

Stripe webhooks notify your server when events happen (charge.succeeded, invoice.paid, customer.subscription.updated). You register an HTTPS endpoint, and Stripe POSTs events to it with a signature you must verify.

## Webhook Endpoint Setup

### Express.js

```javascript
const express = require('express');
const stripe = require('stripe')(process.env.STRIPE_SECRET_KEY);

// Use raw body parser for webhook verification
app.post(
  '/webhooks/stripe',
  express.raw({ type: 'application/json' }),
  async (req, res) => {
    const sig = req.headers['stripe-signature'];
    const webhookSecret = process.env.STRIPE_WEBHOOK_SECRET;

    let event;
    try {
      // Construct and verify the event
      event = stripe.webhooks.constructEvent(req.body, sig, webhookSecret);
    } catch (err) {
      console.error('Webhook signature verification failed:', err.message);
      // Return 400 so Stripe knows verification failed
      return res.status(400).send(`Webhook Error: ${err.message}`);
    }

    // Process the event
    console.log(`Received webhook event: ${event.type}`);

    try {
      switch (event.type) {
        case 'payment_intent.succeeded':
          await handlePaymentIntentSucceeded(event.data.object);
          break;

        case 'payment_intent.payment_failed':
          await handlePaymentIntentFailed(event.data.object);
          break;

        case 'charge.refunded':
          await handleChargeRefunded(event.data.object);
          break;

        case 'customer.subscription.updated':
          await handleSubscriptionUpdated(event.data.object);
          break;

        case 'invoice.payment_failed':
          await handleInvoicePaymentFailed(event.data.object);
          break;

        default:
          console.warn(`Unhandled event type: ${event.type}`);
      }

      // Acknowledge receipt to Stripe
      res.json({ received: true });
    } catch (error) {
      console.error('Error processing webhook:', error);
      // Return 500 so Stripe retries
      res.status(500).json({ error: error.message });
    }
  }
);

// Event handlers
async function handlePaymentIntentSucceeded(paymentIntent) {
  const { metadata, amount, currency, customer } = paymentIntent;
  console.log(`Payment succeeded: ${amount / 100} ${currency.toUpperCase()}`);
  
  // Update order status in database
  await db.orders.update(
    { stripePaymentIntentId: paymentIntent.id },
    { status: 'paid', confirmedAt: new Date() }
  );
  
  // Send confirmation email
  await emailService.sendOrderConfirmation(metadata.orderId);
}

async function handlePaymentIntentFailed(paymentIntent) {
  const { metadata, last_payment_error } = paymentIntent;
  console.error(
    `Payment failed for order ${metadata.orderId}: ${last_payment_error.message}`
  );
  
  // Mark order as payment pending
  await db.orders.update(
    { stripePaymentIntentId: paymentIntent.id },
    { status: 'payment_failed' }
  );
  
  // Send retry email
  await emailService.sendPaymentRetryEmail(metadata.orderId);
}

async function handleChargeRefunded(charge) {
  const { amount, refunded, amount_refunded } = charge;
  console.log(
    `Charge refunded: $${amount / 100} (refunded: $${amount_refunded / 100})`
  );
  
  // Update order/transaction
  await db.transactions.update(
    { stripeChargeId: charge.id },
    { refundedAmount: amount_refunded, status: 'refunded' }
  );
}

async function handleSubscriptionUpdated(subscription) {
  const { id, customer, status, current_period_end } = subscription;
  console.log(`Subscription updated: ${id}, status: ${status}`);
  
  // Update customer subscription record
  await db.subscriptions.update(
    { stripeSubscriptionId: id },
    {
      status,
      renewsAt: new Date(current_period_end * 1000),
    }
  );
}

async function handleInvoicePaymentFailed(invoice) {
  const { customer, amount_due, payment_error } = invoice;
  console.error(`Invoice payment failed: ${customer}, amount due: ${amount_due}`);
  
  // Notify customer of payment failure
  await emailService.sendInvoicePaymentFailedEmail(customer);
}
```

### FastAPI (Python)

```python
from fastapi import FastAPI, Request, HTTPException
import stripe
import hmac
import hashlib
import os

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET")

app = FastAPI()

@app.post("/webhooks/stripe")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, webhook_secret
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError as e:
        raise HTTPException(status_code=400, detail="Invalid signature")

    # Handle the event
    if event["type"] == "payment_intent.succeeded":
        payment_intent = event["data"]["object"]
        print(f"Payment succeeded: {payment_intent['id']}")
        await handle_payment_succeeded(payment_intent)

    elif event["type"] == "payment_intent.payment_failed":
        payment_intent = event["data"]["object"]
        print(f"Payment failed: {payment_intent['id']}")
        await handle_payment_failed(payment_intent)

    elif event["type"] == "customer.subscription.updated":
        subscription = event["data"]["object"]
        print(f"Subscription updated: {subscription['id']}")
        await handle_subscription_updated(subscription)

    return {"status": "success"}


async def handle_payment_succeeded(payment_intent):
    # Update database
    pass

async def handle_payment_failed(payment_intent):
    # Handle failure
    pass

async def handle_subscription_updated(subscription):
    # Update subscription
    pass
```

## Webhook Security Best Practices

### 1. Always Verify the Signature

Never trust the webhook content without verifying the `stripe-signature` header. Stripe signs webhooks with your webhook secret using HMAC-SHA256.

```javascript
// ✅ CORRECT: Verify signature before processing
const event = stripe.webhooks.constructEvent(
  req.body, // raw request body (Buffer)
  req.headers['stripe-signature'],
  webhookSecret
);
```

```javascript
// ❌ WRONG: Skip verification
const event = JSON.parse(req.body);
// Attacker can forge events
```

### 2. Store Webhook Secret Securely

- Never commit webhook secrets to source control
- Load from environment variables
- Rotate webhook secrets periodically
- Use different secrets for test and live environments

```javascript
// ✅ CORRECT
const webhookSecret = process.env.STRIPE_WEBHOOK_SECRET;

// ❌ WRONG
const webhookSecret = "whsec_..."; // hardcoded in code
```

### 3. Use Raw Body for Verification

The signature is computed over the raw request body, not the parsed JSON. Express body parsers can mangle the raw body; use `express.raw()`.

```javascript
// ✅ CORRECT: Use raw body
app.post('/webhooks/stripe', express.raw({ type: 'application/json' }), ...);

// ❌ WRONG: Using parsed JSON
app.use(express.json()); // Don't apply to webhook endpoint
app.post('/webhooks/stripe', (req, res) => {
  // req.body is a parsed object, signature verification fails
});
```

### 4. Return 200 Quickly, Process Asynchronously

Stripe expects a 200 response within 30 seconds. Process the event asynchronously or queue it.

```javascript
// ✅ CORRECT: Queue and acknowledge
app.post('/webhooks/stripe', express.raw({ type: 'application/json' }), (req, res) => {
  event = stripe.webhooks.constructEvent(...);
  
  // Acknowledge receipt immediately
  res.json({ received: true });
  
  // Process asynchronously (don't await here)
  processWebhookEvent(event).catch(err => console.error(err));
});

// Process event in background
async function processWebhookEvent(event) {
  // Database updates, emails, etc.
}
```

### 5. Idempotent Event Processing

Stripe retries failed webhooks; process the same event multiple times safely by using the event ID.

```javascript
async function handlePaymentIntentSucceeded(paymentIntent) {
  const eventId = paymentIntent.id; // Unique per payment
  
  // Check if already processed
  const existing = await db.processedEvents.findOne({ stripeEventId: eventId });
  if (existing) {
    console.log('Event already processed');
    return;
  }
  
  // Process
  await db.orders.update(...);
  
  // Record that we processed it
  await db.processedEvents.insert({ stripeEventId: eventId, processedAt: new Date() });
}
```

## Common Webhook Events

| Event | When It Fires | Typical Action |
|---|---|---|
| `payment_intent.succeeded` | Payment charged successfully | Mark order as paid, send confirmation |
| `payment_intent.payment_failed` | Card declined or timeout | Send retry email, update order status |
| `charge.refunded` | Refund processed | Update transaction, refund inventory |
| `customer.subscription.created` | Subscription started | Update customer record, activate features |
| `customer.subscription.updated` | Billing cycle extended or plan changed | Update renewal date, sync features |
| `customer.subscription.deleted` | Subscription canceled | Revoke access, send cancellation email |
| `invoice.payment_failed` | Recurring charge failed | Send payment failure notice, retry logic |
| `charge.dispute.created` | Chargeback filed | Alert support, gather evidence |

## Testing Webhooks Locally

### Using Stripe CLI

```bash
# Install Stripe CLI (https://stripe.com/docs/stripe-cli)
# Forward Stripe events to your local endpoint
stripe listen --api-key sk_test_... --forward-to localhost:3000/webhooks/stripe

# In another terminal, trigger test events
stripe trigger payment_intent.succeeded
stripe trigger charge.refunded
```

### Manual Testing

Use the Stripe Dashboard: Developers > Webhooks > Your Endpoint > Send Test Event.

### Testing Signature Verification

```javascript
// Test that signature verification works
const crypto = require('crypto');

function generateTestSignature(payload, secret) {
  const timestamp = Math.floor(Date.now() / 1000);
  const signedContent = `${timestamp}.${payload}`;
  const signature = crypto
    .createHmac('sha256', secret)
    .update(signedContent)
    .digest('hex');
  return `t=${timestamp},v1=${signature}`;
}

// Use this signature in your test
const testSig = generateTestSignature(JSON.stringify(testEvent), webhookSecret);
```

## Webhook Endpoint Registration

Register your webhook endpoint in Stripe Dashboard > Developers > Webhooks:

1. Endpoint URL: `https://yourdomain.com/webhooks/stripe`
2. Events: Select events to subscribe to (payment_intent.*, customer.subscription.*, charge.refunded, etc.)
3. Version: Use latest API version
4. Copy the Signing Secret (whsec_...) to your `.env` file

**Note:** Stripe Dashboard webhook endpoints can only be accessed over HTTPS. For local development, use Stripe CLI.
