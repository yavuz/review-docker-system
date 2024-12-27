import { defineEndpoint } from '@directus/extensions-sdk';
import Stripe from 'stripe';

export default defineEndpoint((router, { services, logger }) => {
    const { ItemsService } = services;
    const stripe = new Stripe('');
    const endpointSecret = '';

    // Webhook log kaydı için yardımcı fonksiyon
    async function logWebhook(req: any, event: Stripe.Event, status: string, error?: string) {
        const webhookLogService = new ItemsService('stripe_webhook_logs', {
            schema: req.schema
        });

        await webhookLogService.createOne({
            event_type: event.type,
            event_id: event.id,
            status: status,
            error_message: error,
            data: event,
            date_created: new Date()
        });
    }

    router.get('/', (_req, res) => res.send('Hello, World!'));

	router.post('/webhook', async (req: any, res) => {
        const signature = req.headers['stripe-signature'];
        let event: Stripe.Event;

        try {
            if (!req.rawBody || !signature) {
                logger.error('Webhook hatası: Raw body veya imza eksik');
                return res.status(400).send('Raw body veya imza eksik');
            }

            event = stripe.webhooks.constructEvent(
                req.rawBody,
                signature,
                endpointSecret
            );

            logger.info(`Webhook alındı: ${event.type} ***************************************`);
            logger.info(`İşlenen event tipi: ${event.type}`);

            // Her event'i logla
            await logWebhook(req, event, 'processing');

            switch (event.type) {
                case 'checkout.session.completed':
                    const checkoutSession = event.data.object as Stripe.Checkout.Session;
                    console.log("------------- Checkout session completed -------------");
                    console.log(checkoutSession);
                    
                    if (checkoutSession.mode === 'subscription') {
                        const subscriptionService = new ItemsService('subscriptions', {
                            schema: req.schema
                        });

                        const subscription = await stripe.subscriptions.retrieve(checkoutSession.subscription as string);
                        
                        console.log("------------- Subscription -------------");
                        console.log(subscription);

                        // Invoice'dan payment_intent bilgisini al
                        const invoice = await stripe.invoices.retrieve(subscription.latest_invoice as string);
                        const paymentIntentId = invoice.payment_intent as string;

                        // Paket bilgisini bul
                        const packagesService = new ItemsService('packages', {
                            schema: req.schema
                        });

                        const packageService = await packagesService.readByQuery({
                            filter: {
                                _and: [
                                    { stripe_price_id: subscription.plan.id },
                                    { stripe_product_id: subscription.plan.product }
                                ]
                            }
                        });

                        const packageId = packageService.length > 0 ? packageService[0].id : null;

                        // Ödeme kaydı oluştur
                        const paymentService = new ItemsService('payments', {
                            schema: req.schema
                        });

                        const payment_id = await paymentService.createOne({
                            user_id: checkoutSession.client_reference_id,
                            stripe_payment_id: paymentIntentId,
                            amount: (subscription.items.data[0].price.unit_amount || 0) / 100,
                            currency: subscription.currency,
                            status: 'completed',
                            date_created: new Date(),
                            metadata: checkoutSession.metadata
                        });

                        console.log("------------- Payment -------------");
                        console.log(payment_id);

                        // Mevcut subscription'ı kontrol et
                        const existingSubscription = await subscriptionService.readByQuery({
                            filter: {
                                user_id: checkoutSession.client_reference_id,
                                status: { _in: ['active', 'passive'] }
                            }
                        });

                        if (existingSubscription.length > 0) {
                            // Mevcut aboneliği güncelle
                            await subscriptionService.updateOne(existingSubscription[0].id, {
                                stripe_subscription_id: subscription.id,
                                start_date: new Date(subscription.current_period_start * 1000),
                                end_date: new Date(subscription.current_period_end * 1000),
                                cancel_at_period_end: subscription.cancel_at_period_end,
                                payment_status: subscription.status,
                                package_id: packageId,
                                payment_id: payment_id,
                                status: 'active'
                            });
                        } else {
                            // Yeni abonelik oluştur
                            await subscriptionService.createOne({
                                user_id: checkoutSession.client_reference_id,
                                stripe_subscription_id: subscription.id,
                                start_date: new Date(subscription.current_period_start * 1000),
                                end_date: new Date(subscription.current_period_end * 1000),
                                cancel_at_period_end: subscription.cancel_at_period_end,
                                payment_status: subscription.status,
                                package_id: packageId,
                                payment_id: payment_id,
                                status: 'active'
                            });
                        }

                        if (checkoutSession.customer_email) {
                            // Kullanıcının stripe_customer_id'sini güncelle
                            const userService = new ItemsService('directus_users', {
                                schema: req.schema
                            });

                            await userService.updateByQuery(
                                { filter: { email: checkoutSession.customer_email } },
                                {
                                    stripe_customer_id: checkoutSession.customer,
                                    package_id: packageId
                                }
                            );
                        }
                    }
                    break;

                case 'invoice.payment_succeeded':
                    const successfulInvoice = event.data.object as Stripe.Invoice;
                    
                    const paymentService = new ItemsService('payments', {
                        schema: req.schema
                    });

                    const userService = new ItemsService('directus_users', {
                        schema: req.schema
                    });

                    // Stripe customer id'ye göre kullanıcıyı bul
                    const user = await userService.readByQuery({
                        filter: { stripe_customer_id: successfulInvoice.customer },
                        limit: 1,
                        fields: ['*']
                    });

                    if (!user?.data?.length) {
                        throw new Error('Kullanıcı bulunamadı');
                    }

                    // Önce aynı stripe_payment_id ile kayıt var mı kontrol et
                    const existingPayment = await paymentService.readByQuery({
                        filter: { stripe_payment_id: successfulInvoice.payment_intent as string },
                        limit: 1
                    });

                    let newPayment_id;
                    
                    // Eğer aynı ödeme kaydı yoksa yeni kayıt oluştur
                    if (!existingPayment?.data?.length) {
                        newPayment_id = await paymentService.createOne({
                            user_id: user.length > 0 ? user[0].id : null,
                            stripe_payment_id: successfulInvoice.payment_intent as string,
                            amount: (successfulInvoice.amount_paid || 0) / 100,
                            currency: successfulInvoice.currency,
                            status: 'completed',
                            date_created: new Date(),
                            metadata: successfulInvoice.metadata
                        });
                    } else {
                        newPayment_id = existingPayment.data[0].id;
                    }

                    // Abonelik varsa güncelle
                    if (successfulInvoice.subscription) {
                        const subscriptionService = new ItemsService('subscriptions', {
                            schema: req.schema
                        });

                        const subscription = await stripe.subscriptions.retrieve(successfulInvoice.subscription as string);
                        
                        await subscriptionService.updateByQuery(
                            { filter: { stripe_subscription_id: subscription.id } },
                            {
                                payment_status: subscription.status,
                                end_date: new Date(subscription.current_period_end * 1000),
                                payment_id: newPayment_id
                            }
                        );
                    }
                    break;

                case 'customer.subscription.deleted':
                    const deletedSubscription = event.data.object as Stripe.Subscription;
                    
                    const subscriptionServiceForDelete = new ItemsService('subscriptions', {
                        schema: req.schema
                    });

                    await subscriptionServiceForDelete.updateByQuery(
                        { filter: { stripe_subscription_id: deletedSubscription.id } },
                        {
                            status: 'cancelled',
                            payment_status: deletedSubscription.status,
                            end_date: new Date(deletedSubscription.ended_at ? deletedSubscription.ended_at * 1000 : Date.now())
                        }
                    );
                    break;

                case 'customer.subscription.created':
                    const newSubscription = event.data.object as Stripe.Subscription;
                    // Yeni abonelik veritabanına kaydet
                    break;

                case 'customer.subscription.updated':
                    const updatedSubscription = event.data.object as Stripe.Subscription;
                    // Abonelik güncellemelerini veritabanına yansıt
                    break;

                case 'invoice.payment_failed':
                    const failedInvoice = event.data.object as Stripe.Invoice;
                    // Yinelenen ödeme başarısız olduğunda kullanıcıyı bilgilendir
                    break;

                case 'payment_intent.succeeded':
                    console.log(req.rawBody);
                    /*
                    const paymentIntent = event.data.object as Stripe.PaymentIntent;
                    logger.info(`Başarılı ödeme: ${paymentIntent.id}`);

                    // Checkout session'dan user_id'yi al
                    const sessions = await stripe.checkout.sessions.list({
                        payment_intent: paymentIntent.id
                    });
                    const userSession = sessions.data[0];

                    console.log("------------- User Session -------------");
                    console.log(userSession);
                    
                    const paymentServiceForIntent = new ItemsService('payments', {
                        schema: req.schema
                    });

                    let userId = null;
                    const userServiceForIntent = new ItemsService('directus_users', {
                        schema: req.schema
                    });

                    const user = await userServiceForIntent.readOne({
                        filters: {
                            stripe_customer_id: paymentIntent.customer
                        }
                    });

                    if (user) {
                        userId = user.id;
                    }

                    await paymentServiceForIntent.createOne({
                        stripe_payment_id: paymentIntent.id,
                        amount: paymentIntent.amount,
                        currency: paymentIntent.currency,
                        status: 'completed',
                        created_at: new Date(),
                        metadata: paymentIntent.metadata,
                        user_id: userId || null
                    });

                    console.log("------------- New Payment -------------");
                    console.log(newPayment_id);
                    */

                    break;

                case 'payment_intent.payment_failed':
                    const failedPayment = event.data.object as Stripe.PaymentIntent;
                    logger.warn(`Başarısız ödeme: ${failedPayment.id}`);
                    break;

                default:
                    logger.info(`İşlenmeyen event tipi: ${event.type}`);
            }

            await logWebhook(req, event, 'completed');
            res.json({ received: true });

        } catch (err) {
            const error = err as Error;
            logger.error(`Webhook Hatası: ${error.message}`, error);

            // Eğer event tanımlıysa log kaydı oluştur
            if (typeof event !== 'undefined') {
                await logWebhook(req, event, 'failed', error.message);
            }

            res.status(400).send(`Webhook Hatası: ${error}`);
        }
    });
});
