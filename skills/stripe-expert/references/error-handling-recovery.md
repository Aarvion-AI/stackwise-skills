# Error Handling and Recovery

## Stripe Error Types

Stripe errors fall into several categories:

| Error Type | HTTP Status | Meaning | Retry? |
|---|---|---|---|
| `CardError` | 402 | Card was declined | Yes, retry with different card |
| `RateLimitError` | 429 | Too many requests | Yes, with exponential backoff |
| `AuthenticationError` | 401 | Invalid API key or auth failed | No, check credentials |
| `APIConnectionError` | - | Network failure, can't reach Stripe | Yes, with backoff |
| `APIError` (generic) | 500+ | Server error on Stripe side | Yes, with backoff |
| `InvalidRequestError` | 400 | Bad request parameters | No, fix and retry |

## Handling Card Errors

Card errors are the most common; customers should see specific messages.

```javascript
const stripe = require('stripe')(process.env.STRIPE_SECRET_KEY);

async function processPayment(paymentMethodId, amount) {
  try {
    const paymentIntent = await stripe.paymentIntents.create({
      amount,
      currency: 'usd',
      payment_method: paymentMethodId,
      confirm: true,
      return_url: 'https://example.com/return',
    });

    if (paymentIntent.status === 'succeeded') {
      return { success: true, intentId: paymentIntent.id };
    } else if (paymentIntent.status === 'requires_action') {
      // Customer needs to authenticate (3D Secure)
      return {
        success: false,
        requiresAction: true,
        clientSecret: paymentIntent.client_secret,
        message: 'Please complete the authentication',
      };
    }
  } catch (error) {
    if (error.type === 'StripeCardError') {
      // Card was declined
      return {
        success: false,
        error: error.message, // "Your card was declined"
        code: error.code, // 'card_declined', 'insufficient_funds', etc.
        declineCode: error.decline_code, // Specific reason
      };
    } else if (error.type === 'StripeRateLimitError') {
      // Too many requests, retry with backoff
      return { success: false, error: 'Too many requests, please try again later' };
    } else if (error.type === 'StripeAuthenticationError') {
      // API key issue
      console.error('Stripe authentication failed:', error.message);
      return { success: false, error: 'Payment service error' };
    } else if (error.type === 'StripeAPIConnectionError') {
      // Network failure, likely transient
      return { success: false, error: 'Network error, please try again' };
    } else if (error.type === 'StripeAPIError') {
      // Server error, retry
      return { success: false, error: 'Payment service temporarily unavailable' };
    }
  }
}
```

## Card Decline Reasons

Present human-friendly messages to customers:

```javascript
const declineMessages = {
  generic_decline: 'Your card was declined. Please try a different card.',
  insufficient_funds: 'Insufficient funds. Please check your account balance.',
  lost_card: 'Your card was reported lost.',
  stolen_card: 'Your card was reported stolen.',
  expired_card: 'Your card has expired. Please enter a new card.',
  incorrect_cvc: 'The security code is incorrect.',
  processing_error: 'An error occurred processing your payment. Please try again.',
  card_velocity_exceeded: 'Too many attempts. Please wait and try again.',
  authentication_required: 'Your card issuer requires authentication. Please complete the 3D Secure verification.',
};

async function handleCardError(decline_code) {
  return declineMessages[decline_code] || declineMessages.generic_decline;
}
```

## Retry Logic with Exponential Backoff

Transient errors (network, rate limit, server errors) should retry:

```javascript
async function paymentWithRetry(fn, maxRetries = 3) {
  let lastError;

  for (let attempt = 0; attempt < maxRetries; attempt++) {
    try {
      return await fn();
    } catch (error) {
      lastError = error;

      // Don't retry card errors or authentication errors
      if (
        error.type === 'StripeCardError' ||
        error.type === 'StripeAuthenticationError' ||
        error.type === 'StripeInvalidRequestError'
      ) {
        throw error;
      }

      // Retry transient errors
      if (
        error.type === 'StripeRateLimitError' ||
        error.type === 'StripeAPIConnectionError' ||
        error.type === 'StripeAPIError'
      ) {
        const backoffMs = Math.pow(2, attempt) * 1000; // 1s, 2s, 4s
        console.warn(`Attempt ${attempt + 1} failed, retrying in ${backoffMs}ms...`);
        await sleep(backoffMs);
      } else {
        throw error;
      }
    }
  }

  throw lastError;
}

// Usage
const result = await paymentWithRetry(() =>
  stripe.paymentIntents.create({
    amount: 9900,
    currency: 'usd',
    payment_method: paymentMethodId,
    confirm: true,
  })
);

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
```

## Handling Webhook Failures

If your webhook endpoint is unreachable or returns an error, Stripe retries:

- Immediately
- 5 seconds later
- 5 minutes later
- 30 minutes later
- 2 hours later
- 5 hours later
- 10 hours later
- 24 hours later

### Graceful Webhook Handling

```javascript
app.post(
  '/webhooks/stripe',
  express.raw({ type: 'application/json' }),
  async (req, res) => {
    const sig = req.headers['stripe-signature'];

    let event;
    try {
      event = stripe.webhooks.constructEvent(req.body, sig, webhookSecret);
    } catch (err) {
      return res.status(400).send(`Webhook Error: ${err.message}`);
    }

    // Acknowledge receipt immediately
    res.json({ received: true });

    // Process asynchronously, handle errors gracefully
    try {
      await processEvent(event);
    } catch (error) {
      console.error('Webhook processing failed:', error);
      // Log to error tracking (Sentry, DataDog)
      // Stripe will retry automatically
      // Alert ops team if critical
    }
  }
);

async function processEvent(event) {
  // Wrap database operations in try/catch
  try {
    switch (event.type) {
      case 'payment_intent.succeeded':
        await handlePaymentIntentSucceeded(event.data.object);
        break;
      // ... other cases
    }
  } catch (error) {
    if (error.code === 'ECONNREFUSED') {
      // Database connection failed, will retry
      throw error;
    } else if (error.message.includes('timeout')) {
      // Timeout, retry
      throw error;
    } else {
      // Non-transient error, log and continue
      console.error('Unrecoverable error:', error);
    }
  }
}
```

## Idempotency for Payment Operations

Stripe automatically handles retries if your webhook endpoint fails. Ensure operations are idempotent:

```javascript
// Database helper: upsert-style operation
async function handlePaymentIntentSucceeded(paymentIntent) {
  const { id, metadata } = paymentIntent;

  // Check if already processed
  const existing = await db.orders.findOne({
    stripePaymentIntentId: id,
  });

  if (existing) {
    console.log(`Payment ${id} already recorded, skipping`);
    return existing;
  }

  // Process for first time
  const order = await db.orders.updateOne(
    { id: metadata.orderId },
    {
      status: 'paid',
      stripePaymentIntentId: id,
      confirmedAt: new Date(),
    }
  );

  return order;
}
```

## Handling Payment Intent Failures

A PaymentIntent can fail for reasons beyond the card error:

```javascript
async function handlePaymentIntentPaymentFailed(paymentIntent) {
  const { id, last_payment_error, metadata } = paymentIntent;

  console.error(`Payment failed for order ${metadata.orderId}:`, last_payment_error);

  const failureReason = last_payment_error.type;
  let customerMessage = 'Payment failed. Please try again.';

  switch (failureReason) {
    case 'card_error':
      customerMessage = `Card declined: ${last_payment_error.message}`;
      break;
    case 'authentication_error':
      customerMessage = 'Authentication failed. Please try a different card.';
      break;
    case 'rate_limit_error':
      customerMessage = 'Please wait a moment and try again.';
      break;
    case 'api_error':
      customerMessage = 'Payment service temporarily unavailable. We will retry.';
      break;
  }

  // Update order to show failure
  await db.orders.updateOne(
    { id: metadata.orderId },
    {
      status: 'payment_failed',
      failureReason: last_payment_error.code,
      failureMessage: last_payment_error.message,
      lastAttempt: new Date(),
    }
  );

  // Send email with retry options
  await emailService.sendPaymentFailedEmail(metadata.orderId, customerMessage);
}
```

## Refund Error Handling

Refunds can fail if already refunded or disputed:

```javascript
async function refundCharge(chargeId, amount) {
  try {
    const refund = await stripe.refunds.create({
      charge: chargeId,
      amount, // optional; full refund if omitted
    });

    console.log(`Refund created: ${refund.id}`);
    return { success: true, refundId: refund.id };
  } catch (error) {
    if (error.code === 'charge_already_refunded') {
      return { success: false, error: 'Charge has already been refunded' };
    } else if (error.code === 'charge_disputed') {
      return {
        success: false,
        error: 'Charge is under dispute. Contact support.',
      };
    } else if (error.code === 'charge_not_refundable') {
      return {
        success: false,
        error: 'Charge cannot be refunded in its current state',
      };
    } else {
      console.error('Refund error:', error);
      return { success: false, error: 'Refund failed. Please try again.' };
    }
  }
}
```

## Handling Webhook Signature Verification Failures

Invalid signatures indicate a potential security issue:

```javascript
app.post(
  '/webhooks/stripe',
  express.raw({ type: 'application/json' }),
  async (req, res) => {
    const sig = req.headers['stripe-signature'];
    const webhookSecret = process.env.STRIPE_WEBHOOK_SECRET;

    let event;
    try {
      event = stripe.webhooks.constructEvent(req.body, sig, webhookSecret);
    } catch (err) {
      // Signature verification failed
      console.error('Webhook signature verification failed:', err.message);

      // Alert security team
      await alertService.sendSecurityAlert({
        type: 'WEBHOOK_VERIFICATION_FAILURE',
        endpoint: '/webhooks/stripe',
        ip: req.ip,
        timestamp: new Date(),
      });

      // Return 400 so Stripe knows verification failed
      return res.status(400).send(`Webhook Error: ${err.message}`);
    }

    // Continue with processing
    res.json({ received: true });
  }
);
```

## Error Monitoring and Alerting

```javascript
async function withErrorTracking(fn, context) {
  try {
    return await fn();
  } catch (error) {
    // Log to error tracking service
    if (typeof Sentry !== 'undefined') {
      Sentry.captureException(error, {
        tags: { context, stripeError: !!error.type },
        extra: {
          stripeType: error.type,
          stripeCode: error.code,
        },
      });
    }

    // Critical errors: alert ops
    if (error.type === 'StripeAuthenticationError') {
      await alertService.sendCriticalAlert(
        'Stripe API authentication failed - check keys'
      );
    }

    throw error;
  }
}

// Usage
await withErrorTracking(() => processPayment(paymentMethodId, amount), 'payment_process');
```

## Testing Error Scenarios

Use Stripe test cards to trigger specific errors:

```javascript
const testCards = {
  success: '4242 4242 4242 4242',
  decline: '4000 0000 0000 0002',
  decline_insufficient_funds: '4000 0000 0000 9995',
  decline_lost_card: '4000 0000 0000 9987',
  decline_stolen_card: '4000 0000 0000 9979',
  authentication_required: '4000 0025 0000 3155',
  authentication_required_3ds2: '4000 0025 0000 3155',
};

// In tests:
// - Try decline card, verify error message shown to user
// - Try authentication card, verify 3D Secure flow triggered
// - Simulate network error, verify retry logic works
// - Verify webhook retry logic handles failures gracefully
```
