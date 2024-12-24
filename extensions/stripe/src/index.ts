import { defineEndpoint } from '@directus/extensions-sdk';
import Stripe from 'stripe';

export default defineEndpoint((router, { services, exceptions, logger }) => {
    const { ItemsService } = services;
    const stripe = new Stripe('sk_test_51OADZIHso5U3tKeT40LCYVdGl0g9UduMYky6HZiE3w9me6iST4YRnz0iKSzqo1sjAkE5olZ7A01ki3OHphSXdJZI00bELI51Xc');
    const endpointSecret = 'whsec_66455dea19c5d30ac6f210314573005f34f4d69e2072c3e7765ee2d5d7cbbdee';

    router.get('/', (_req, res) => res.send('Hello, World!'));

	router.post('/webhook', async (req, res) => {
        const signature = req.headers['stripe-signature'];

        try {
			console.log(req.rawBody);
            if (!req.rawBody || !signature) {
                logger.error('Webhook hatası: Raw body veya imza eksik');
                return res.status(400).send('Raw body veya imza eksik');
            }

            const event = stripe.webhooks.constructEvent(
                req.rawBody,
                signature,
                endpointSecret
            );

            logger.info(`İşlenen event tipi: ${event.type}`);

            switch (event.type) {
                case 'payment_intent.succeeded':
                    const paymentIntent = event.data.object as Stripe.PaymentIntent;
                    logger.info(`Başarılı ödeme: ${paymentIntent.id}`);

                    // Directus'ta ödeme kaydı oluştur
                    const paymentService = new ItemsService('payments', {
                        schema: req.schema
                    });

                    try {
                        await paymentService.createOne({
                            stripe_payment_id: paymentIntent.id,
                            amount: paymentIntent.amount,
                            currency: paymentIntent.currency,
                            status: 'completed',
                            created_at: new Date(),
                            metadata: paymentIntent.metadata
                        });
                    } catch (createError) {
                        logger.error(`Ödeme kaydı oluşturulamadı: ${createError.message}`);
                        return res.status(403).send(`Ödeme kaydı oluşturulamadı: ${createError.message}`);
                    }
                    break;

                case 'payment_intent.payment_failed':
                    const failedPayment = event.data.object as Stripe.PaymentIntent;
                    logger.warn(`Başarısız ödeme: ${failedPayment.id}`);
                    break;

                default:
                    logger.info(`İşlenmeyen event tipi: ${event.type}`);
            }

            res.json({ received: true });

        } catch (err) {
            const error = err as Error;
            logger.error(`Webhook Hatası: ${error.message}`);
            res.status(400).send(`Webhook Hatası: ${error.message}`);
        }
    });
});
