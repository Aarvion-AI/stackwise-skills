---
name: stripe-expert
description: Use when working on payment flows, checkout integration, billing, or webhook handling. Builds production-ready Stripe payment systems with security best practices, webhook validation, idempotency, and error recovery. Invoke for payment checkout, subscription management, webhook integration, and PCI-compliance audits.
license: MIT
metadata:
  version: "0.1.0"
  category: backend
  frameworks: "Stripe API v2024+, Stripe SDKs (Node, Python, Java, Go)"
  triggers: stripe, payment, checkout, webhook, subscription, billing, customer portal, refund
  related: nestjs-expert, fastapi-expert, fastify-expert, go-expert
---

# Stripe Expert

A payment systems engineer who builds secure, resilient Stripe integrations with webhook validation, idempotency, error recovery, and compliance built in.

## Safety and Authorization

- Start with local, read-only inspection: review existing payment code, Stripe API keys scope, webhook secret location.
- Ask for explicit user approval before creating or modifying live Stripe resources, publishing webhooks to production endpoints, testing refunds or captures on real charges, or accessing customer payment data.
- Before any payment operation, show the exact Stripe operation, customer impact, idempotency handling, and rollback path.
- Never weaken webhook signature validation, idempotency checks, or error recovery to make a workflow pass. Redact API keys and webhook secrets from commands, logs, screenshots, and evidence.
- Test all payment flows in Stripe test mode before moving to live mode.

## When to Use This Skill

- Add a Stripe Checkout or Payment Element to a web or mobile app
- Build custom payment forms with Stripe.js and PaymentIntent
- Implement server-side webhook handlers for payment events (charge.succeeded, customer.subscription.updated, etc.)
- Set up subscription billing, recurring charges, or tiered pricing
- Recover from payment failures: retry logic, dunning, customer notifications
- Audit PCI compliance, API key rotation, and webhook secret management
- Debug payment flow issues: intent status mismatches, webhook delivery failures, idempotency errors

## Core Workflow

1. **Analyze** - Inspect the app structure, locate Stripe API keys (test and live), find webhook handlers, review existing payment code for idempotency and error handling patterns
2. **Design** - Choose payment flow (Checkout, Payment Element, custom form) based on app architecture; sketch customer journey; identify Stripe events to listen for
3. **Implement** - Create or update payment form, Stripe server-side logic, webhook handler; always include idempotency keys and signature validation
4. **Verify types/lint** - Run `npm run lint` or equivalent; validate environment variables (STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET) are never logged
5. **Test payment flow** - Trigger a test payment using Stripe test card numbers; confirm PaymentIntent status progresses correctly; verify webhook delivery in test mode; simulate failure scenarios (card decline, timeout)
6. **Prove it works** - Run the app locally or in staging; manually complete a payment using test card; check Stripe Dashboard > Events to confirm all expected webhooks fired; verify customer record in Stripe Dashboard

## Reference Guide

Load detailed guidance only when the task needs it:

| Topic | Reference | Load When |
|---|---|---|
| Checkout and Payment Elements | `references/checkout-and-payment-elements.md` | Building a checkout page or adding Payment Element to a form |
| Webhook Handling and Security | `references/webhook-handling-security.md` | Implementing event listeners for payment status changes |
| API Authentication and Key Management | `references/api-authentication-keys.md` | Setting up Stripe client/secret keys, rotating keys, managing environments |
| Subscription and Recurring Billing | `references/subscription-recurring-billing.md` | Implementing subscriptions, tiered pricing, usage-based billing, or customer portal |
| Error Handling and Recovery | `references/error-handling-recovery.md` | Handling payment failures, retries, dunning, and refund scenarios |
| Testing and Idempotency | `references/testing-idempotency.md` | Writing payment tests, using test card numbers, idempotency keys, webhook simulation |

## Key Patterns

### 1. Payment Intent with Idempotency

```javascript
// Node.js - create a PaymentIntent with idempotency to ensure exactly-once semantics
const stripe = require('stripe')(process.env.STRIPE_SECRET_KEY);

// Idempotency key prevents double-charging if the request is retried
const idempotencyKey = `order-${orderId}-${Date.now()}`;

const paymentIntent = await stripe.paymentIntents.create(
  {
    amount: Math.round(totalCents), // always in cents
    currency: 'usd',
    customer: customerId, // link to Stripe Customer
    metadata: { orderId, userId }, // attach context for webhooks
    description: 'Order #123 - Acme Corp',
  },
  { idempotencyKey } // Stripe reuses intent if called again with same key
);
```

### 2. Webhook Handler with Signature Verification

```javascript
// Express.js - receive and verify a webhook from Stripe
const express = require('express');
const stripe = require('stripe')(process.env.STRIPE_SECRET_KEY);

app.post('/webhooks/stripe', express.raw({ type: 'application/json' }), async (req, res) => {
  const sig = req.headers['stripe-signature'];
  const webhookSecret = process.env.STRIPE_WEBHOOK_SECRET;

  let event;
  try {
    // Always validate the signature before processing the event
    event = stripe.webhooks.constructEvent(req.body, sig, webhookSecret);
  } catch (err) {
    console.error('Webhook signature verification failed:', err.message);
    return res.status(400).send(`Webhook Error: ${err.message}`);
  }

  // Handle specific payment events
  switch (event.type) {
    case 'payment_intent.succeeded':
      const paymentIntent = event.data.object;
      console.log(`Payment succeeded for order ${paymentIntent.metadata.orderId}`);
      // Mark order as paid in your database
      break;

    case 'payment_intent.payment_failed':
      const failedIntent = event.data.object;
      console.error(`Payment failed for order ${failedIntent.metadata.orderId}`);
      // Send retry email to customer
      break;

    case 'customer.subscription.updated':
      const subscription = event.data.object;
      console.log(`Subscription updated: ${subscription.id}`);
      break;

    default:
      console.log(`Unhandled event type: ${event.type}`);
  }

  res.json({ received: true });
});
```

### 3. Server-side Card Processing with PaymentMethod

```python
# Python / FastAPI - process a payment method on the server
import stripe
from fastapi import FastAPI, HTTPException

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

@app.post("/pay")
async def create_payment(payment_data: PaymentRequest):
    try:
        # Create a PaymentIntent server-side
        intent = stripe.PaymentIntent.create(
            amount=payment_data.amount_cents,
            currency="usd",
            customer=payment_data.stripe_customer_id,
            payment_method=payment_data.payment_method_id,
            off_session=True,  # Store payment for future charges
            confirm=True,      # Charge immediately
            metadata={"order_id": payment_data.order_id},
        )

        if intent.status == "succeeded":
            return {"status": "success", "intent_id": intent.id}
        elif intent.status == "requires_action":
            # Customer needs to authenticate (3D Secure)
            return {"status": "action_required", "client_secret": intent.client_secret}
        else:
            raise HTTPException(status_code=402, detail=f"Payment failed: {intent.status}")

    except stripe.error.CardError as e:
        # Card was declined
        raise HTTPException(status_code=402, detail=f"Card declined: {e.user_message}")
    except stripe.error.StripeError as e:
        # Other Stripe errors
        raise HTTPException(status_code=500, detail=f"Payment error: {str(e)}")
```

## Common Mistakes

- **Forgetting idempotency keys** - Without idempotency keys, network retries can cause duplicate charges. Always include `{ idempotencyKey }` when creating PaymentIntents, Charges, or Invoices.

- **Skipping webhook signature verification** - Processing webhooks without validating the `stripe-signature` header opens the door to forged payment events. Always call `stripe.webhooks.constructEvent()` before handling events.

- **Storing card data client-side** - Never store full card numbers or CVVs in your database or logs. Use Stripe Elements or Payment Method for client-side collection; store only the PaymentMethod ID.

- **Trusting client state for payment status** - Don't rely on the frontend to report payment success. Always verify with Stripe via webhooks or API calls to check PaymentIntent status server-side.

- **Ignoring webhook retry logic** - Stripe retries failed webhooks; don't process the same event twice. Use `event.id` as an idempotency key when writing to your database, or store delivered webhook IDs in a set.

- **Testing on live mode by accident** - Test payment code with `sk_test_*` keys and test card numbers (e.g., `4242 4242 4242 4242`). Never use live keys during development or in test suites.
