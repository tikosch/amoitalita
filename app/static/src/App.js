import React, { useState } from 'react';
import axios from 'axios';

function App() {
  const [address, setAddress] = useState('');
  const [time, setTime] = useState('');
  const [price, setPrice] = useState(null);
  const [error, setError] = useState('');

  const calculatePrice = async () => {
    if (!address || !time) {
      setError('Please enter both address and time.');
      return;
    }

    try {
      const response = await axios.post('/api/calculate_price', {
        address,
        time: parseInt(time),
      });

      if (response.data.price) {
        setPrice(`Estimated Price: ${response.data.price} KZT`);
        setError('');
      } else {
        setError('Error calculating price.');
      }
    } catch (err) {
      setError('Error fetching price from server.');
    }
  };

  return (
    <div style={{ padding: '20px', fontFamily: 'Arial' }}>
      <h2>Yandex Delivery Price Calculator</h2>
      <div>
        <label>Address:</label>
        <input
          type="text"
          value={address}
          onChange={(e) => setAddress(e.target.value)}
          placeholder="Enter destination address"
          style={{ marginLeft: '10px', marginBottom: '10px', padding: '5px' }}
        />
      </div>
      <div>
        <label>Time (minutes):</label>
        <input
          type="number"
          value={time}
          onChange={(e) => setTime(e.target.value)}
          placeholder="Time in minutes"
          style={{ marginLeft: '10px', marginBottom: '10px', padding: '5px' }}
        />
      </div>
      <button onClick={calculatePrice} style={{ padding: '5px 10px' }}>
        Calculate Price
      </button>
      {price && <div style={{ marginTop: '10px', color: 'green' }}>{price}</div>}
      {error && <div style={{ marginTop: '10px', color: 'red' }}>{error}</div>}
    </div>
  );
}

export default App;
