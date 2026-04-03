---
id: account-settings
title: Gérer les paramètres du compte
description: Guide pour mettre à jour votre profil, mot de passe et préférences
roles: [admin, focal_point]
category: account
keywords: [profil, mot de passe, paramètres, préférences, changer mot de passe, mettre à jour profil]
pages:
  - /account-settings
---

# Gérer les paramètres du compte

Ce flux de travail vous guide dans la mise à jour de vos paramètres de compte, informations de profil et mot de passe.

## Prérequis

- Connecté au système

## Étapes

### Étape 1 : Naviguer vers les paramètres du compte
- **Page** : `/account-settings`
- **Sélecteur** : `.bg-white.p-6.rounded-lg.shadow-md`
- **Action** : Accédez à vos paramètres de compte
- **Aide** : C'est votre page de paramètres de compte où vous pouvez mettre à jour vos informations personnelles, préférences et mot de passe.
- **Texte d'action** : Suivant

### Étape 2 : Mettre à jour les informations personnelles
- **Page** : `/account-settings`
- **Sélecteur** : `input[name="name"], input[name="phone"], #profile_color`
- **Action** : Modifiez vos détails de profil
- **Aide** : Mettez à jour votre nom d'affichage, numéro de téléphone et couleur de profil. Votre adresse e-mail ne peut pas être modifiée - c'est votre identifiant de connexion.
- **Texte d'action** : Suivant

### Étape 3 : Configurer les préférences
- **Page** : `/account-settings`
- **Sélecteur** : `input[name="chatbot_enabled"], select[name="language"]`
- **Action** : Définissez vos préférences
- **Aide** : Activez ou désactivez l'assistant de chat IA et définissez votre langue préférée pour l'interface.
- **Texte d'action** : Suivant

### Étape 4 : Enregistrer les modifications
- **Page** : `/account-settings`
- **Sélecteur** : `button[type="submit"]`
- **Action** : Enregistrez vos paramètres
- **Aide** : Cliquez sur "Enregistrer les modifications" pour appliquer vos mises à jour. Vos paramètres seront enregistrés immédiatement.
- **Texte d'action** : Compris

## Exigences du mot de passe

Votre mot de passe doit :
- Avoir au moins 8 caractères
- Contenir au moins une lettre majuscule
- Contenir au moins une lettre minuscule
- Contenir au moins un chiffre
- Ne pas être un mot de passe couramment utilisé

## Conseils

- Changez votre mot de passe régulièrement pour la sécurité
- Activez les notifications par e-mail pour rester informé des dates limites
- Définissez votre fuseau horaire correct pour voir les heures de date limite précises
- Gardez vos informations de contact à jour

## Flux de travail connexes

- [Voir les missions](../focal-point/view-assignments.md) - Vérifiez vos tâches en attente
