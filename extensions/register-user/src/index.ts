// extensions/hooks/auto-seller-role/index.js

export default ({ action }, { services, database }) => {
	action('users.create', async ({ payload, accountability }) => {
	  try {
		// Önce yeni oluşturulan kullanıcıyı email'e göre bulalım
		const user = await database.raw('SELECT id FROM directus_users WHERE email = ?', [payload.email])
		  .then(result => result[0][0]);
  
		if (!user) {
		  throw new Error('User not found');
		}
  
		// Seller rolünü database'den bulalım
		const roleResult = await database.raw('SELECT id FROM directus_roles WHERE name = ?', ['seller']);
		const sellerRole = roleResult[0][0];
  
		if (!sellerRole) {
		  throw new Error('Seller role not found');
		}
  
		// Direkt database update kullanalım
		await database.raw('UPDATE directus_users SET role = ? WHERE id = ?', [
		  sellerRole.id,
		  user.id
		]);
  
		console.log(`Role updated for user: ${payload.email}`);
	  } catch (error) {
		console.error('Error in auto-seller-role hook:', error);
		console.log('Error details:', {
		  message: error.message,
		  stack: error.stack
		});
	  }
	});
  };