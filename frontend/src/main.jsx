/**
 * Purpose: Boots the React application, attaches it to the HTML root, enables
 * client-side routing, and loads the global visual styles.
 */
/**
 * Purpose: Boots React, enables client-side routing, and loads global styles.
 */
import React from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import App from './App';
import './styles.css';
import './ai.css';

createRoot(document.getElementById('root')).render(<BrowserRouter><App /></BrowserRouter>);
